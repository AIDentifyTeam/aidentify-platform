from django.conf import settings
from django.shortcuts import render

def landing_page(request):
    return render(request, 'landing/index.html', {
        "APP_VERSION": getattr(settings, "VERSION", "0.0.0"),
        "APP_VERSION_NAME": getattr(settings, "VERSION_NAME", "Default")
    })