import time
import redis
import boto3
import os
from botocore.exceptions import ClientError
from botocore.config import Config
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Waits for Redis and MinIO to be ready'

    def handle(self, *args, **options):
        self.stdout.write("Checking services...")

        # Redis check
        redis_ready = False
        redis_host = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0').split('//')[1].split(':')[0]
        
        # We will use the service name 'redis' instead of 'redis_broker' for consistency
        # as your docker-compose file uses 'redis' as the service name.
        redis_host = 'redis'
        
        for i in range(5):
            try:
                r = redis.Redis(host=redis_host, port=6379)
                if r.ping():
                    redis_ready = True
                    break
            except Exception as e:
                self.stdout.write(f"Redis not ready, retrying... ({i+1}/5) Error: {str(e)}")
                time.sleep(2)

        # MinIO check using boto3
        minio_ready = False
        minio_endpoint = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
        minio_access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        minio_secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
        minio_region = os.getenv('MINIO_REGION', 'us-east-1')

        for i in range(5):
            try:
                s3 = boto3.client(
                    's3',
                    aws_access_key_id=minio_access_key,
                    aws_secret_access_key=minio_secret_key,
                    endpoint_url=minio_endpoint,
                    region_name=minio_region,
                    config=Config(s3={'addressing_style': 'path'})
                )
                
                # Simple operation to verify connection
                s3.list_buckets()
                minio_ready = True
                break
            except ClientError as e:
                self.stdout.write(f"MinIO not ready, retrying... ({i+1}/5) Error: {e}")
                time.sleep(2)
            except Exception as e:
                self.stdout.write(f"Waiting for MinIO... ({e})")
                time.sleep(2)

        if not redis_ready:
            raise CommandError("Redis service not available!")
        if not minio_ready:
            raise CommandError("MinIO service not available!")

        self.stdout.write(self.style.SUCCESS("All services are ready!"))