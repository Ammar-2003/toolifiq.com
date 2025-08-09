# tasks.py
import os
from celery import shared_task
from django.conf import settings
from .models import FileConversion
from .converters import PdfToHtmlConverter
from storages.backends.s3boto3 import S3Boto3Storage
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def convert_pdf_to_html_task(self, task_id):
    """
    Celery task to convert PDF to HTML using MinIO for storage
    """
    try:
        storage = S3Boto3Storage()
        task = FileConversion.objects.get(task_id=task_id)
        task.status = 'PROCESSING'
        task.save()
        
        # Download the file from MinIO to local temp
        original_path = task.original_file.name
        local_input_path = f'/tmp/{os.path.basename(original_path)}'
        
        with storage.open(original_path, 'rb') as remote_file:
            with open(local_input_path, 'wb') as local_file:
                local_file.write(remote_file.read())
        
        # Process conversion
        converter = PdfToHtmlConverter(open(local_input_path, 'rb'))
        
        if task.conversion_type == 'formatted':
            output_path = converter.convert_to_formatted_html()
        else:
            output_path = converter.convert_to_clean_text()
        
        # Upload result back to MinIO
        output_filename = f'converted/{task_id}/{os.path.basename(output_path)}'
        
        with open(output_path, 'rb') as f:
            storage.save(output_filename, f)
        
        # Update task with result
        task.converted_file.name = output_filename
        task.status = 'COMPLETED'
        task.save()
        
        # Cleanup local files
        converter.cleanup()
        os.unlink(local_input_path)
        
        return True
    
    except Exception as e:
        logger.error(f"PDF conversion failed for task {task_id}: {str(e)}", exc_info=True)
        if 'task' in locals():
            task.status = 'FAILED'
            task.error_message = str(e)
            task.save()
        return False