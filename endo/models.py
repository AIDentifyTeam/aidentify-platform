from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class Doctor(AbstractUser):
    username = None  # remove username field entirely
    email = models.EmailField(unique=True)  # <-- make email unique explicitly
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    specialization = models.CharField(max_length=100, default="Endodontist")
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Patient(models.Model):
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='patients')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    birth_date = models.DateField()
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True) 

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def age(self):
        from datetime import date
        today = date.today()
        return (
            today.year - self.birth_date.year -
            ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )
        

class VisitHistory(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='visits')
    tooth_number = models.CharField(max_length=10)
    visit_date = models.DateField(auto_now_add=True)
    tooth_image = models.ImageField(upload_to='tooth_images/', null=True, blank=True)
    answers = models.JSONField(default=dict)  # Stores the diagnosis question answers
    pulp_diagnosis = models.CharField(max_length=100)
    periapical_disease = models.CharField(max_length=100)
    etiology = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.patient} - Tooth {self.tooth_number} on {self.visit_date}"


class ResearchPaper(models.Model):
    title = models.CharField(max_length=255)
    authors = models.TextField()
    journal = models.CharField(max_length=255)
    abstract = models.TextField()
    year = models.IntegerField(null=True, blank=True, help_text="Year of journal publication (optional)")
    added_date = models.DateTimeField(auto_now_add=True)  # used for sorting newest added

    def __str__(self):
        return self.title


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ('reminder', 'Reminder'),
        ('system_update', 'System Update'),
        ('new_case_review', 'New Case Review'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)  # Sort by latest added

    def __str__(self):
        return f"[{self.category}] {self.title}"


class NotificationReadStatus(models.Model):
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('doctor', 'notification')