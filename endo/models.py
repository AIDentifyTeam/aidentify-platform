from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.contrib.auth.models import BaseUserManager
from django.db.models import Q

class DoctorManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class Doctor(AbstractUser):
    username = None  # remove username field entirely
    email = models.EmailField(unique=True)  # <-- make email unique explicitly
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    specialization = models.CharField(max_length=100, default="Endodontist")
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = DoctorManager() # type: ignore
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
class Patient(models.Model):
    class Sex(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"
        OTHER = "Other", "Other"

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patients'
    )

    # Required
    first_name = models.CharField(max_length=100)
    last_name  = models.CharField(max_length=100)

    # Optional
    birth_date = models.DateField(blank=True, null=True)
    phone      = models.CharField(max_length=20, blank=True, null=True)
    email      = models.EmailField(blank=True, null=True)
    sex        = models.CharField(max_length=10, choices=Sex.choices, blank=True, null=True)

    # Optional clinic system ID entered by doctor
    patient_id = models.CharField(max_length=20, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Uniqueness only when patient_id is present, and scoped to the doctor
            models.UniqueConstraint(
                fields=['doctor', 'patient_id'],
                condition=Q(patient_id__isnull=False),
                name='uniq_patient_id_per_doctor'
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def age(self):
        from datetime import date
        if not self.birth_date:
            return None
        today = date.today()
        return (today.year - self.birth_date.year
                - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day)))
        

class VisitHistory(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='visits')
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='visits')
    tooth_number = models.CharField(max_length=10)
    visit_date = models.DateTimeField(auto_now_add=True)
    tooth_image = models.ImageField(upload_to='tooth_images/', null=True, blank=True)
    answers = models.JSONField(default=dict)  # Stores the diagnosis question answers
    pulp_diagnosis = models.CharField(max_length=100, null=True, blank=True)
    periapical_disease = models.CharField(max_length=100, null=True, blank=True)
    etiology = models.CharField(max_length=100, null=True, blank=True)
    results = models.JSONField(default=list, blank=True)
    case_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    
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