# Toolifiq — File & Media Tools Platform
Toolifiq offers an array of file utilities: image converters (JPG ⇄ PNG), PDF tools (PDF→PNG, PDF→DOCX extract), compressors, encoders/decoders, and developer-friendly REST endpoints. Built for reliability, scale, and maintainability.

# Key features

REST API endpoints for every tool (JSON responses + job IDs)

Asynchronous processing with Celery + Redis for long-running conversions

File storage via S3-compatible backend (MinIO for dev, AWS S3 for prod)

Dockerized with docker-compose for local dev and Kubernetes manifests for production

Rate limiting + job queue priorities + concurrency control

Optional user accounts, API keys, and quota management

Responsive frontend with drag & drop upload, progress, preview, and download

Audit logs and monitoring (Prometheus + Grafana) and Sentry for errors

# Tech stack

Backend: Python, Django, Django REST Framework

Async: Celery, Redis

Storage: MinIO (dev), AWS S3 (prod), django-storages

Converters: pillow, pdf2image, PyMuPDF/fitz, python-docx or docx2pdf integrations

Containerization: Docker, docker-compose (local), Kubernetes (prod)

CI/CD: GitHub Actions (or GitLab CI)

Monitoring: Prometheus, Grafana, Sentry

Auth: Django auth (users) + JWT for API or API keys

Frontend: Django templates + JS
