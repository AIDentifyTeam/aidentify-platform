# 🚀 AIdentify Platform – Installation Guide

Welcome to the AIdentify backend installation guide. This document walks you through setting up the Django backend in a local or production environment using `pyenv`, virtualenv, and Gunicorn.

---

## 📁 1. Clone the Repository

```bash
git clone git@github.com:AIDentifyTeam/aidentify-platform.git
cd aidentify-platform
```

---

## 🐍 2. Install Python via pyenv (Recommended)

Make sure you’ve installed pyenv and system build dependencies.

```bash
pyenv install 3.10.6
pyenv global 3.10.6
```

---

## 🌱 3. Create and Activate a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔐 4. Create the `.env` File

Copy the example and edit it:

```bash
cp example.env .env
nano .env
```

Fill in your production secrets (e.g., secret key, DB credentials, etc.).

---

## ⚙️ 5. Run Django Setup Commands

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

---

## 🧪 6. Test the Application Locally

```bash
gunicorn --bind 0.0.0.0:8000 aidentify_platform.wsgi:application
```

Open your browser at:  
[http://localhost:8000](http://localhost:8000)  
or use your server IP.

---

