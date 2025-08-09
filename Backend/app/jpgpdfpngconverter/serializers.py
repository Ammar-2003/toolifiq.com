from rest_framework import serializers
from .models import FileConversion

class FileConversionSerializer(serializers.ModelSerializer):
    converted_file_url = serializers.SerializerMethodField()

    class Meta:
        model = FileConversion
        fields = ['id', 'original_file', 'converted_file', 'converted_file_url', 'conversion_type', 'created_at']

    def get_converted_file_url(self, obj):
        if obj.converted_file:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.converted_file.url) if request else obj.converted_file.url
        return None