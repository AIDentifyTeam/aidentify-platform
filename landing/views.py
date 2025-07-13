from django.http import HttpResponse

def home(request):
    return HttpResponse("<h1>Welcome to AIdentify</h1><p>This is our landing page.</p>")
