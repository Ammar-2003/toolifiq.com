from django.db import models
from django.conf import settings
from django.core.files.storage import default_storage

class FileConversion(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    task_id = models.CharField(max_length=255, unique=True)
    original_file = models.FileField(upload_to='pdf_uploads/')
    converted_file = models.FileField(upload_to='html_outputs/', null=True, blank=True)
    conversion_type = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)
    
    def get_download_url(self):
        """Generate a signed download URL for the converted file"""
        if not self.converted_file:
            return None
        
        storage = default_storage(settings.DEFAULT_FILE_STORAGE)()
        if hasattr(storage, 'url'):
            return storage.url(self.converted_file.name)
        return None
    
    def __str__(self):
        return f"{self.task_id} - {self.status}"