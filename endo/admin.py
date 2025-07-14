from django.contrib import admin
from .models import Doctor, Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

class DoctorAdmin(BaseUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'specialization', 'is_staff')
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'specialization', 'profile_image')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

admin.site.register(Doctor, DoctorAdmin)
admin.site.register(Notification)
admin.site.register(NotificationReadStatus)
admin.site.register(ResearchPaper)
admin.site.register(Patient)
admin.site.register(VisitHistory)