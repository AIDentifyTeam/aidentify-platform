from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Doctor

admin.site.register(Doctor, UserAdmin)