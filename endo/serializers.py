# endo/serializers/auth.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

from endo.models import Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory

Doctor = get_user_model()

class DoctorRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Doctor
        fields = ['email', 'first_name', 'last_name', 'password', 'specialization']

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
        read_only_fields = ['id', 'username']
        
class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            'id',
            'first_name',
            'last_name',
            'birth_date',
            'phone',
            'email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['doctor'] = request.user
        return super().create(validated_data)
    
class VisitHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitHistory
        fields = '__all__'
        read_only_fields = ['doctor', 'visit_date', 'pulp_diagnosis', 'periapical_disease', 'etiology']

    def calculate_diagnoses(self, answers):
        # 🔧 Placeholder: Replace this with real logic
        return {
            'pulp_diagnosis': 'Pending Diagnosis',
            'periapical_disease': 'Pending Diagnosis',
            'etiology': 'Pending Diagnosis'
        }

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['doctor'] = request.user

        # Run placeholder logic to populate calculated fields
        answers = validated_data.get('answers', {})
        diagnoses = self.calculate_diagnoses(answers)
        validated_data.update(diagnoses)

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
