# AIdentify Backend (Django + DRF)

Django REST backend for AIdentify EndoApp. Provides JWT-secured APIs for Doctors, Patients, VisitHistory, Notifications, and ResearchPaper. Supports authenticated media uploads and rule-based diagnosis endpoints.

## Features
- Django REST Framework APIs (CRUD for core models)
- JWT auth (access/refresh)
- Media uploads / secure file serving
- Pagination, filtering, and ordering where applicable
- Ready for web CORS + CSRF where needed
- Healthcheck endpoint (optional)

## Core Models
- **Doctor**
- **Patient**
- **VisitHistory**
- **Notification**
- **ResearchPaper**

## API (examples)
- `POST /api/token/`, `POST /api/token/refresh/`
- `GET/POST /api/patients/`, `GET/PUT/PATCH/DELETE /api/patients/{id}/`
- `GET/POST /api/visits/`
- `GET /api/research-papers/`
- `GET /api/notifications/`
- Media: `POST /api/uploads/` (or direct model file fields) → served under `/media/`

## Configuration
Use environment variables:
- `DJANGO_SECRET_KEY` (required)
- `DEBUG` (`0`/`1`)
- `ALLOWED_HOSTS` (comma-separated)
- `DATABASE_URL` (or `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`)
- `CORS_ALLOWED_ORIGINS` (comma-separated web origins)
- `MEDIA_ROOT` (default: `./media`)
- `MEDIA_URL` (default: `/media/`)
- **JWT** (if using SimpleJWT):
  - `SIMPLE_JWT_ACCESS_LIFETIME=5` (minutes)
  - `SIMPLE_JWT_REFRESH_LIFETIME=7` (days)

## Local Development
```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Visit `http://localhost:8000/admin/` and your `/api/` endpoints.

## Media & Uploads
- Ensure `MEDIA_ROOT` exists and app server has write permissions.
- In development, `django.views.static.serve` can serve `/media/`.
- In production, serve `/media/` via Nginx; block directory listing.

## CORS
Enable `django-cors-headers` and set `CORS_ALLOWED_ORIGINS` to frontend origins.

## Tests & Quality
```
pytest
ruff check .
black .
```

## Deployment
- Use Postgres
- Run `collectstatic` if using static files
- Behind Nginx with HTTPS and secure cookies
- Configure `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`
