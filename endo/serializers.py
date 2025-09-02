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
    # Optional helper to clear image via PATCH {"remove_tooth_image": true}
    remove_tooth_image = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = VisitHistory
        fields = '__all__'
        read_only_fields = [
            'doctor', 'visit_date', 'pulp_diagnosis', 'periapical_disease',
            'etiology', 'case_id', 'results'
        ]

    def _apply_diagnosis_to_dict(self, data: dict) -> None:
        answers = data.get("answers", {}) or {}
        dx = clean_json(diagnosis_engine.diagnose(answers))
        data["results"] = dx
        if dx and isinstance(dx, list) and dx and isinstance(dx[0], dict):
            first = dx[0]
            data["pulp_diagnosis"] = first.get("pulp_diagnosis", "")
            data["periapical_disease"] = first.get("periapical_disease", "")
            data["etiology"] = first.get("etiology", "")
        else:
            data["pulp_diagnosis"] = ""
            data["periapical_disease"] = ""
            data["etiology"] = ""

    def _apply_diagnosis_to_instance(self, instance: VisitHistory) -> None:
        dx = clean_json(diagnosis_engine.diagnose(instance.answers or {}))
        instance.results = dx
        if dx and isinstance(dx, list) and dx and isinstance(dx[0], dict):
            first = dx[0]
            instance.pulp_diagnosis = first.get("pulp_diagnosis", "") # type: ignore
            instance.periapical_disease = first.get("periapical_disease", "") # type: ignore
            instance.etiology = first.get("etiology", "") # type: ignore
        else:
            instance.pulp_diagnosis = ""
            instance.periapical_disease = ""
            instance.etiology = ""

    def create(self, validated_data):
        validated_data.pop("remove_tooth_image", None)
        self._apply_diagnosis_to_dict(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # forbid changing patient on an existing visit
        if "patient" in validated_data and validated_data["patient"].id != instance.patient_id:
            raise serializers.ValidationError({"patient": "Cannot change patient of an existing visit."})

        # handle optional image removal flag
        if validated_data.pop("remove_tooth_image", False):
            if instance.tooth_image:
                instance.tooth_image.delete(save=False)
            instance.tooth_image = None

        # detect whether answers changed; if not provided, keep current
        answers_changed = "answers" in validated_data

        # perform the base update (writes answers/tooth_number/etc.)
        instance = super().update(instance, validated_data)

        # recompute diagnosis when answers changed (or always, if you prefer)
        if answers_changed:
          self._apply_diagnosis_to_instance(instance)
          instance.save(update_fields=["results","pulp_diagnosis","periapical_disease","etiology"])

        return instance


class EtiologyAvailabilityIn(serializers.Serializer):
    # Page-1 answers only (P..X). Values are strings like "Yes", "No", etc.
    answers = serializers.DictField(
        child=serializers.CharField(allow_blank=False, trim_whitespace=True),
        required=True,
    )

    # Optional: reject unknown keys early (remove if you want to allow anything)
    def validate_answers(self, value):
        allowed = {"P", "Q", "R", "S", "T", "U", "V", "W", "X", "chief_complaint"}
        unknown = set(value.keys()) - allowed
        if unknown:
            raise serializers.ValidationError(
                f"Unknown question id(s): {', '.join(sorted(unknown))}"
            )
        return value
    
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
