# endo/serializers/auth.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

from endo.diagnosis_engine import DiagnosisEngine
from endo.models import Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory
from endo.utils import clean_json
from django.core.validators import RegexValidator

Doctor = get_user_model()
diagnosis_engine = DiagnosisEngine("endo/data/pulp.xlsx")


phone_validator = RegexValidator(
    regex=r'^[0-9+\-() ]{7,}$',
    message="Failed to create new patient, please enter a valid phone number/email."
)

class DoctorRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    profile_image = serializers.ImageField(allow_null=True, required=False)
    
    class Meta:
        model = Doctor
        fields = [
            'id', 'username', 'email',
            'first_name', 'last_name',
            'specialization', 'profile_image', 'password'
        ]
    

    def create(self, validated_data):
        user = Doctor(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            specialization=validated_data.get('specialization', 'Endodontist')
        )
        user.set_password(validated_data['password'])
        user.save()
        return user


class DoctorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'specialization', 'profile_image']
        read_only_fields = ['id', 'username', 'email'] 
        
class PatientSerializer(serializers.ModelSerializer):
    patient_id = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    class Meta:
        model = Patient
        fields = [
            'id',
            'first_name',
            'last_name',
            'birth_date',
            'patient_id',
            'phone',
            'email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']  # <-- removed patient_id from here

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['doctor'] = request.user
        return super().create(validated_data)


    
class VisitHistorySerializer(serializers.ModelSerializer):   
    class Meta:
        model = VisitHistory
        fields = '__all__'
        read_only_fields = ['doctor', 'visit_date', 'pulp_diagnosis', 'periapical_disease', 'etiology', 'case_id', 'results']

    def create(self, validated_data):
        answers = validated_data.get("answers", {})
        diagnoses = diagnosis_engine.diagnose(answers)
        diagnoses = clean_json(diagnoses)

        validated_data["results"] = diagnoses

        if diagnoses and isinstance(diagnoses, list) and len(diagnoses) > 0:
            first = diagnoses[0]
            if isinstance(first, dict):
                validated_data["pulp_diagnosis"] = first.get("pulp_diagnosis", "")
                validated_data["periapical_disease"] = first.get("periapical_disease", "")
                validated_data["etiology"] = first.get("etiology", "")

        return super().create(validated_data)


    
class ResearchPaperSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchPaper
        fields = '__all__'
        
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'description', 'category', 'created_at']

class NotificationReadStatusSerializer(serializers.ModelSerializer):
    notification = NotificationSerializer(read_only=True)

    class Meta:
        model = NotificationReadStatus
        fields = ['id', 'notification', 'is_read', 'read_at']
