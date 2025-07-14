from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Notification, NotificationReadStatus

Doctor = get_user_model()

@receiver(post_save, sender=Notification)
def create_notification_read_status(sender, instance, created, **kwargs):
    if created:
        # Create NotificationReadStatus for all doctors when notification created
        doctors = Doctor.objects.all()
        statuses = [
            NotificationReadStatus(doctor=doctor, notification=instance)
            for doctor in doctors
        ]
        NotificationReadStatus.objects.bulk_create(statuses)
