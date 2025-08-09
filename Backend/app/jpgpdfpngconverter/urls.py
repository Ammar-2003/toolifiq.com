from django.urls import path
from .views import PdfToJpgView, JpgToPdfView, PngToPdfView, PdfToPngView , PdfToWebpView , PdfToWordView , PdfToHtmlView , ConversionStatusView

urlpatterns = [
    path('pdf-to-jpg/', PdfToJpgView.as_view()),
    path('jpg-to-pdf/', JpgToPdfView.as_view()),
    path('png-to-pdf/', PngToPdfView.as_view()),
    path('pdf-to-png/', PdfToPngView.as_view()),
    path('pdf-to-webp/', PdfToWebpView.as_view()),
    path('pdf-to-word/', PdfToWordView.as_view()),
    path('pdf-to-html/', PdfToHtmlView.as_view()),
    path('conversion-status/', ConversionStatusView.as_view()),
]