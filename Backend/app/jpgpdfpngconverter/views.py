from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from .models import FileConversion
from .converters import FileConverter
import os
from django.conf import settings
from django.http import FileResponse
import zipfile
import fitz  # PyMuPDF
from PIL import Image
import uuid  # For unique IDs
import tempfile
import logging
from .converters import PdfToWordConverter
from .tasks import convert_pdf_to_html_task
# from django.core.files.storage import default_storage
from minio.error import S3Error
from minio import Minio
from datetime import timedelta


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class PdfToJpgView(APIView):
    def post(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_obj = request.FILES['file']
        conversion = None
        temp_pdf_path = None
        temp_output_dir = None
        zip_path = None

        try:
            # Validate file size (10MB max)
            if file_obj.size > 20 * 1024 * 1024:
                raise ValidationError('File size exceeds 20MB limit')

            converter = FileConverter(file_obj, 'pdf2jpg')
            conversion = converter.create_conversion_record()
            
            # Create temp directory for PDF
            temp_pdf_dir = os.path.join(settings.MEDIA_ROOT, 'temp', str(conversion.id))
            os.makedirs(temp_pdf_dir, exist_ok=True)
            temp_pdf_path = os.path.join(temp_pdf_dir, file_obj.name)
            
            # Save uploaded file
            with open(temp_pdf_path, 'wb+') as f:
                for chunk in file_obj.chunks():
                    f.write(chunk)
            
            # Open PDF to check page count
            doc = fitz.open(temp_pdf_path)
            page_count = len(doc)
            doc.close()
            
            # For single-page PDFs
            if page_count == 1:
                output_jpg_path = converter.get_output_path('jpg')
                os.makedirs(os.path.dirname(output_jpg_path), exist_ok=True)
                
                converter.convert_pdf_to_jpg(temp_pdf_path, output_jpg_path)
                
                if not os.path.exists(output_jpg_path):
                    raise RuntimeError("Conversion failed - no output file created")
                
                converter.save_conversion(output_jpg_path, 'jpg')
                
                return Response({
                    'id': conversion.id,
                    'original_file': conversion.original_file.url,
                    'converted_file': conversion.converted_file.url,
                    'page_count': 1,
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)
            
            # For multi-page PDFs
            else:
                # Create output directory for JPGs
                temp_output_dir = os.path.join(temp_pdf_dir, 'jpg_output')
                os.makedirs(temp_output_dir, exist_ok=True)
                
                # Convert all pages to JPGs
                doc = fitz.open(temp_pdf_path)
                jpg_files = []
                
                for page_num in range(page_count):
                    page = doc.load_page(page_num)
                    zoom = 96 / 72  # Standard 96 DPI
                    mat = fitz.Matrix(zoom, zoom)
                    
                    pix = page.get_pixmap(
                        matrix=mat,
                        alpha=False,
                        colorspace="RGB",
                        dpi=96
                    )
                    
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    jpg_path = os.path.join(temp_output_dir, f"page_{page_num+1}.jpg")
                    img.save(jpg_path, format='JPEG', quality=85, optimize=True)
                    jpg_files.append(jpg_path)
                
                doc.close()
                
                if not jpg_files:
                    raise RuntimeError("No JPG files were created")
                
                # Create ZIP archive
                zip_filename = f"{os.path.splitext(file_obj.name)[0]}.zip"
                zip_path = os.path.join(temp_pdf_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for jpg_file in jpg_files:
                        arcname = os.path.basename(jpg_file)
                        zipf.write(jpg_file, arcname)
                
                # Save conversion record with ZIP file
                conversion.converted_file.name = f'temp/{conversion.id}/{zip_filename}'
                conversion.save()
                
                return Response({
                    'id': conversion.id,
                    'original_file': conversion.original_file.url,
                    'converted_file': conversion.converted_file.url,
                    'page_count': page_count,
                    'download_url': f'/api/pdf-to-jpg/{conversion.id}/download/',
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Cleanup on failure
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if temp_output_dir and os.path.exists(temp_output_dir):
                for f in os.listdir(temp_output_dir):
                    os.remove(os.path.join(temp_output_dir, f))
                os.rmdir(temp_output_dir)
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            if conversion:
                conversion.delete()
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request, conversion_id):
        """Download the ZIP file (for multi-page PDFs)"""
        try:
            conversion = FileConversion.objects.get(id=conversion_id)
            if not conversion.converted_file.name.endswith('.zip'):
                return Response(
                    {'error': 'Single page conversion - use the direct JPG URL'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            zip_path = conversion.converted_file.path
            
            response = FileResponse(open(zip_path, 'rb'))
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(zip_path)}"'
            response['Content-Type'] = 'application/zip'
            return response
            
        except FileConversion.DoesNotExist:
            return Response(
                {'error': 'Conversion not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Download failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class JpgToPdfView(APIView):
    def post(self, request):
        if 'files' not in request.FILES:
            return Response(
                {'error': 'No files uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_objs = request.FILES.getlist('files')
        conversion = None
        temp_jpg_paths = []
        output_pdf_path = None

        try:
            # Validate all files first
            for file_obj in file_objs:
                if not file_obj.name.lower().endswith(('.jpg', '.jpeg')):
                    raise ValidationError('Only JPG/JPEG files are allowed')
                if file_obj.size > 20 * 1024 * 1024:  # 10MB limit per file
                    raise ValidationError(f'File {file_obj.name} exceeds 20MB size limit')

            # Create conversion record
            converter = FileConverter(file_objs[0], 'jpg2pdf')
            conversion = converter.create_conversion_record()
            
            # Create temp directory
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save all files to temp location
            for i, file_obj in enumerate(file_objs):
                temp_jpg_path = os.path.join(temp_dir, f'temp_{i}_{file_obj.name}')
                with open(temp_jpg_path, 'wb+') as f:
                    for chunk in file_obj.chunks():
                        f.write(chunk)
                temp_jpg_paths.append(temp_jpg_path)
            
            # Prepare output path
            output_pdf_path = converter.get_output_path('pdf')
            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            
            # Convert to PDF (handles both single and multiple files)
            if len(temp_jpg_paths) == 1:
                converter.convert_jpg_to_pdf(temp_jpg_paths[0], output_pdf_path)
            else:
                converter.convert_jpg_to_pdf(temp_jpg_paths, output_pdf_path, is_multiple=True)
            
            # Verify conversion succeeded
            if not os.path.exists(output_pdf_path):
                raise RuntimeError("Conversion failed - no output file created")
            if os.path.getsize(output_pdf_path) == 0:
                raise RuntimeError("Conversion produced empty PDF file")
            
            # Save conversion record
            converter.save_conversion(output_pdf_path, 'pdf')
            
            # Prepare response
            original_files = [{
                'name': f.name,
                'size': f.size,
                'type': f.content_type
            } for f in file_objs]
            
            return Response({
                'id': conversion.id,
                'original_files': original_files,
                'converted_file': conversion.converted_file.url,
                'page_count': len(temp_jpg_paths),
                'status': 'success'
            }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # Clean up temp files
            for path in temp_jpg_paths:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
            if output_pdf_path and os.path.exists(output_pdf_path):
                try:
                    os.remove(output_pdf_path)
                except:
                    pass
            if conversion:
                try:
                    conversion.delete()
                except:
                    pass
                
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PngToPdfView(APIView):
    def post(self, request):
        if 'files' not in request.FILES:
            return Response(
                {'error': 'No files uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_objs = request.FILES.getlist('files')
        conversion = None
        temp_files = []
        output_pdf_path = None

        try:
            # Create conversion record with the first file (we'll track all files in metadata)
            converter = FileConverter(file_objs[0], 'png2pdf')
            conversion = converter.create_conversion_record()
            
            # Store original filenames in conversion metadata
            conversion.metadata = {
                'original_filenames': [file.name for file in file_objs],
                'total_files': len(file_objs)
            }
            conversion.save()
            
            temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save all uploaded files to temp directory
            for i, file_obj in enumerate(file_objs):
                temp_file_path = os.path.join(temp_dir, f'temp_{i}_{file_obj.name}')
                with open(temp_file_path, 'wb+') as f:
                    for chunk in file_obj.chunks():
                        f.write(chunk)
                temp_files.append(temp_file_path)
            
            output_pdf_path = converter.get_output_path('pdf')
            os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
            
            # Convert multiple PNGs to single PDF - no time limit
            converter.convert_png_to_pdf(temp_files, output_pdf_path, is_multiple=True)
            
            if not os.path.exists(output_pdf_path):
                raise RuntimeError("Conversion failed - no output file created")
            
            converter.save_conversion(output_pdf_path, 'pdf')
            
            return Response({
                'id': conversion.id,
                'original_files': [file_obj.name for file_obj in file_objs],
                'converted_file': conversion.converted_file.url,
                'status': 'success',
                'page_count': len(file_objs)
            }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            # Clean up temp files
            for temp_file in temp_files:
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)
            if output_pdf_path and os.path.exists(output_pdf_path):
                os.remove(output_pdf_path)
            if conversion:
                conversion.delete()
                
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PdfToPngView(APIView):
    def post(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_obj = request.FILES['file']
        conversion = None
        temp_pdf_path = None
        temp_output_dir = None

        try:
            # Validate file size (20MB max)
            if file_obj.size > 20 * 1024 * 1024:
                raise ValidationError('File size exceeds 20MB limit')

            converter = FileConverter(file_obj, 'pdf2png')
            conversion = converter.create_conversion_record()
            
            # Create temp directory for PDF
            temp_pdf_dir = os.path.join(settings.MEDIA_ROOT, 'temp', str(conversion.id))
            os.makedirs(temp_pdf_dir, exist_ok=True)
            temp_pdf_path = os.path.join(temp_pdf_dir, file_obj.name)
            
            # Save uploaded file
            with open(temp_pdf_path, 'wb+') as f:
                for chunk in file_obj.chunks():
                    f.write(chunk)
            
            # Create output directory for PNGs
            temp_output_dir = os.path.join(temp_pdf_dir, 'png_output')
            os.makedirs(temp_output_dir, exist_ok=True)
            
            # Convert all pages to PNGs - no time limit
            doc = fitz.open(temp_pdf_path)
            png_files = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = 96 / 72  # Standard 96 DPI
                mat = fitz.Matrix(zoom, zoom)
                
                pix = page.get_pixmap(
                    matrix=mat,
                    alpha=False,
                    colorspace="RGB",
                    dpi=96
                )
                
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                png_path = os.path.join(temp_output_dir, f"page_{page_num+1}.png")
                img.save(png_path, format='PNG', optimize=True, compress_level=6)
                png_files.append(png_path)
            
            doc.close()
            
            if not png_files:
                raise RuntimeError("No PNG files were created")
            
            # Create ZIP archive instead of RAR
            zip_filename = f"{os.path.splitext(file_obj.name)[0]}.zip"
            zip_path = os.path.join(temp_pdf_dir, zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for png_file in png_files:
                    arcname = os.path.basename(png_file)
                    zipf.write(png_file, arcname)
            
            # Save conversion record with ZIP file
            conversion.converted_file.name = f'temp/{conversion.id}/{zip_filename}'
            conversion.save()
            
            return Response({
                'id': conversion.id,
                'original_file': conversion.original_file.url,
                'converted_file': conversion.converted_file.url,
                'page_count': len(png_files),
                'download_url': f'/api/pdf-to-png/{conversion.id}/download/',
                'status': 'success'
            }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Cleanup on failure
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if temp_output_dir and os.path.exists(temp_output_dir):
                for f in os.listdir(temp_output_dir):
                    os.remove(os.path.join(temp_output_dir, f))
                os.rmdir(temp_output_dir)
            if conversion:
                conversion.delete()
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request, conversion_id):
        """Download the ZIP file"""
        try:
            conversion = FileConversion.objects.get(id=conversion_id)
            zip_path = conversion.converted_file.path
            
            response = FileResponse(open(zip_path, 'rb'))
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(zip_path)}"'
            response['Content-Type'] = 'application/zip'
            return response
            
        except FileConversion.DoesNotExist:
            return Response(
                {'error': 'Conversion not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Download failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PdfToWebpView(APIView):
    def post(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_obj = request.FILES['file']
        conversion = None
        temp_pdf_path = None
        temp_output_dir = None
        zip_path = None

        try:
            # Validate file size (20MB max)
            if file_obj.size > 20 * 1024 * 1024:
                raise ValidationError('File size exceeds 20MB limit')

            converter = FileConverter(file_obj, 'pdf2webp')
            conversion = converter.create_conversion_record()
            
            # Create temp directory for PDF
            temp_pdf_dir = os.path.join(settings.MEDIA_ROOT, 'temp', str(conversion.id))
            os.makedirs(temp_pdf_dir, exist_ok=True)
            temp_pdf_path = os.path.join(temp_pdf_dir, file_obj.name)
            
            # Save uploaded file
            with open(temp_pdf_path, 'wb+') as f:
                for chunk in file_obj.chunks():
                    f.write(chunk)
            
            # Open PDF to check page count
            doc = fitz.open(temp_pdf_path)
            page_count = len(doc)
            doc.close()
            
            # For single-page PDFs
            if page_count == 1:
                output_webp_path = converter.get_output_path('webp')
                os.makedirs(os.path.dirname(output_webp_path), exist_ok=True)
                
                converter.convert_pdf_to_webp(temp_pdf_path, output_webp_path)
                
                if not os.path.exists(output_webp_path):
                    raise RuntimeError("Conversion failed - no output file created")
                
                converter.save_conversion(output_webp_path, 'webp')
                
                return Response({
                    'id': conversion.id,
                    'original_file': conversion.original_file.url,
                    'converted_file': conversion.converted_file.url,
                    'page_count': 1,
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)
            
            # For multi-page PDFs
            else:
                # Create output directory for WebPs
                temp_output_dir = os.path.join(temp_pdf_dir, 'webp_output')
                os.makedirs(temp_output_dir, exist_ok=True)
                
                # Convert all pages to WebPs
                doc = fitz.open(temp_pdf_path)
                webp_files = []
                
                for page_num in range(page_count):
                    page = doc.load_page(page_num)
                    zoom = 96 / 72  # Standard 96 DPI
                    mat = fitz.Matrix(zoom, zoom)
                    
                    pix = page.get_pixmap(
                        matrix=mat,
                        alpha=False,
                        colorspace="RGB",
                        dpi=96
                    )
                    
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    webp_path = os.path.join(temp_output_dir, f"page_{page_num+1}.webp")
                    img.save(webp_path, format='WEBP', quality=80, method=6)
                    webp_files.append(webp_path)
                
                doc.close()
                
                if not webp_files:
                    raise RuntimeError("No WebP files were created")
                
                # Create ZIP archive
                zip_filename = f"{os.path.splitext(file_obj.name)[0]}.zip"
                zip_path = os.path.join(temp_pdf_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for webp_file in webp_files:
                        arcname = os.path.basename(webp_file)
                        zipf.write(webp_file, arcname)
                
                # Save conversion record with ZIP file
                conversion.converted_file.name = f'temp/{conversion.id}/{zip_filename}'
                conversion.save()
                
                return Response({
                    'id': conversion.id,
                    'original_file': conversion.original_file.url,
                    'converted_file': conversion.converted_file.url,
                    'page_count': page_count,
                    'download_url': f'/api/pdf-to-webp/{conversion.id}/download/',
                    'status': 'success'
                }, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Cleanup on failure
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
            if temp_output_dir and os.path.exists(temp_output_dir):
                for f in os.listdir(temp_output_dir):
                    os.remove(os.path.join(temp_output_dir, f))
                os.rmdir(temp_output_dir)
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
            if conversion:
                conversion.delete()
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request, conversion_id):
        """Download the ZIP file (for multi-page PDFs)"""
        try:
            conversion = FileConversion.objects.get(id=conversion_id)
            if not conversion.converted_file.name.endswith('.zip'):
                return Response(
                    {'error': 'Single page conversion - use the direct WebP URL'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            zip_path = conversion.converted_file.path
            
            response = FileResponse(open(zip_path, 'rb'))
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(zip_path)}"'
            response['Content-Type'] = 'application/zip'
            return response
            
        except FileConversion.DoesNotExist:
            return Response(
                {'error': 'Conversion not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Download failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class PdfToWordView(APIView):
    """Production-ready PDF to Word API endpoint"""
    
    converter = PdfToWordConverter()
    
    def post(self, request):
        if 'file' not in request.FILES:
            return Response({'error': 'No file uploaded'}, status=400)
        
        file_obj = request.FILES['file']
        temp_files = []
        
        try:
            # Validate input
            if not file_obj.name.lower().endswith('.pdf'):
                return Response({'error': 'Only PDF files are allowed'}, status=400)
            
            max_size = getattr(settings, 'MAX_PDF_UPLOAD_SIZE', 25 * 1024 * 1024)
            if file_obj.size > max_size:
                return Response(
                    {'error': f'File size exceeds {max_size//1024//1024}MB limit'},
                    status=400
                )
            
            # Create temp files
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
                for chunk in file_obj.chunks():
                    tmp_pdf.write(chunk)
                pdf_path = tmp_pdf.name
                temp_files.append(pdf_path)
            
            output_filename = f"{uuid.uuid4()}.docx"
            output_path = os.path.join(settings.MEDIA_ROOT, 'converted', output_filename)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Get conversion mode (default: preserve layout)
            preserve_graphics = request.POST.get('preserve_graphics', 'true').lower() == 'true'
            
            # Perform conversion
            metadata = self.converter.convert_pdf_to_word(
                pdf_path,
                output_path,
                preserve_graphics=preserve_graphics
            )
            
            return Response({
                'converted_file': f'/media/converted/{output_filename}',
                'status': 'success',
                'metadata': metadata
            })
            
        except Exception as e:
            logger.error(f"PDF to Word conversion failed: {str(e)}")
            return Response(
                {'error': f'Conversion failed: {str(e)}'},
                status=500
            )
            
        finally:
            # Clean up temp files
            for file_path in temp_files:
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Error deleting temp file {file_path}: {str(e)}")

class PdfToHtmlView(APIView):
    """
    Asynchronous PDF to HTML conversion API with MinIO storage
    """
    
    def __init__(self):
        # Initialize MinIO client
        self.minio_client = Minio(
            os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
            secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
            secure=False  # Set to True if using HTTPS
        )
        self.bucket_name = os.getenv('MINIO_BUCKET_NAME', 'uploads')

    def post(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file uploaded'},
                status=status.HTTP_400_BAD_REQUEST
            )

        conversion_type = request.data.get('conversion_type', 'formatted')
        if conversion_type not in ['formatted', 'clean']:
            return Response(
                {'error': 'Invalid conversion type'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_obj = request.FILES['file']
        
        try:
            # Validate file size (20MB max)
            if file_obj.size > 20 * 1024 * 1024:
                raise ValidationError('File size exceeds 20MB limit')
            
            # Generate paths
            task_id = str(uuid.uuid4())
            object_name = f"pdf-to-html/{task_id}/{file_obj.name}"
            
            # Ensure bucket exists
            if not self.minio_client.bucket_exists(self.bucket_name):
                self.minio_client.make_bucket(self.bucket_name)
            
            # Upload file to MinIO
            self.minio_client.put_object(
                self.bucket_name,
                object_name,
                file_obj,
                length=file_obj.size,
                content_type=file_obj.content_type
            )
            
            # Create task record
            task = FileConversion.objects.create(
                task_id=task_id,
                original_file=object_name,  # Store full MinIO path
                conversion_type=conversion_type,
                status='PENDING'
            )
            
            # Start async conversion
            try:
                convert_pdf_to_html_task.delay(task_id)
            except Exception as e:
                logger.error(f"Failed to submit Celery task: {str(e)}")
                task.status = 'FAILED'
                task.error_message = 'Failed to queue conversion task'
                task.save()
                raise
            
            return Response({
                'task_id': task_id,
                'status': 'PENDING',
                'conversion_type': conversion_type,
                'status_url': f'/api/conversion-status/{task_id}/'
            }, status=status.HTTP_202_ACCEPTED)
            
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except S3Error as e:
            logger.error(f"MinIO Error: {str(e)}")
            return Response(
                {'error': 'Failed to upload file to storage'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"System Error: {str(e)}")
            return Response(
                {'error': 'Conversion process failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class ConversionStatusView(APIView):
    """
    API to check conversion status and get download URL from MinIO
    """
    
    def __init__(self):
        # Initialize MinIO client
        self.minio_client = Minio(
            os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
            secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
            secure=False  # Set to True if using HTTPS
        )
        self.bucket_name = os.getenv('MINIO_BUCKET_NAME', 'uploads')
    
    def get(self, request, task_id):
        try:
            task = FileConversion.objects.get(task_id=task_id)
            
            response_data = {
                'task_id': task_id,
                'status': task.status,
                'conversion_type': task.conversion_type,
                'created_at': task.created_at,
                'updated_at': task.updated_at
            }
            
            if task.status == 'COMPLETED':
                # Generate presigned URL for download
                try:
                    download_url = self.minio_client.presigned_get_object(
                        self.bucket_name,
                        task.converted_file.name,  # This should be the object path in MinIO
                        expires=timedelta(hours=1)  # URL expires in 1 hour
                    )
                    response_data['download_url'] = download_url
                except S3Error as e:
                    logger.error(f"Failed to generate MinIO download URL: {str(e)}")
                    response_data['error'] = 'Failed to generate download URL'
            
            elif task.status == 'FAILED':
                response_data['error'] = task.error_message
            
            return Response(response_data)
        
        except FileConversion.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error checking conversion status: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to check conversion status'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )