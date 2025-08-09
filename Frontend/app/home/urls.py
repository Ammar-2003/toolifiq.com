from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('wordcounter/', views.wordcounter_view, name='wordcounter'),
    path('jpg-to-pdf/', views.jpgtopdf_view, name='jpg-to-pdf'),
    path('pdf-to-jpg/', views.pdftojpg_view, name='pdf-to-jpg'),
    path('png-to-pdf/', views.pngtopdf_view, name='png-to-pdf'),
    path('pdf-to-png/', views.pdftopng_view, name='pdf-to-png'),
    path('pdf-to-webp/', views.pdftowebp_view, name='pdf-to-webp'),
    path('pdf-to-word/', views.pdftoword_view, name='pdf-to-word'),
    path('pdf-to-html/', views.pdftohtml_view, name='pdf-to-html'),
]