from django.shortcuts import render

def home_view(request):
    return render(request, 'home.html')

def wordcounter_view(request):
    return render(request, 'wordcounter/index.html')

def pdftojpg_view(request):
    return render(request, 'converters/pdf-to-jpg.html')

def jpgtopdf_view(request):
    return render(request, 'converters/jpg-to-pdf.html')

def pdftopng_view(request):
    return render(request, 'converters/pdf-to-png.html')

def pngtopdf_view(request):
    return render(request, 'converters/png-to-pdf.html')

def pdftowebp_view(request):
    return render(request, 'converters/pdf-to-webp.html')

def pdftoword_view(request):
    return render(request, 'converters/pdf-to-word.html')

def pdftohtml_view(request):
    return render(request, 'converters/pdf-to-html.html')