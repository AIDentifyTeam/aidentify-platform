# endo/serializers/auth.py
from rest_framework import serializers
from django.contrib.auth import get_user_model

from endo.diagnosis_service import generate_diagnosis_payload
from endo.models import Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory
from endo.utils import clean_json
from django.core.validators import RegexValidator

Doctor = get_user_model()
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

    # ------------ internal helpers ------------
    def _apply_dx_result_dict(self, data: dict, dx: dict) -> None:
        """
        Put engine output 'dx' into data dict and set the 3 top-level fields
        iff rules_engine produced matches.
        """
        data["results"] = clean_json(dx)
        pulp = peri = etio = ""
        if isinstance(dx, dict) and dx.get("source") == "rules_engine":
            res = dx.get("results") or []
            if isinstance(res, list) and res and isinstance(res[0], dict):
                first = res[0]
                pulp = first.get("pulp_diagnosis", "") or ""
                peri = first.get("periapical_disease", "") or ""
                etio = first.get("etiology", "") or ""
        data["pulp_diagnosis"] = pulp
        data["periapical_disease"] = peri
        data["etiology"] = etio

    def _apply_diagnosis_to_dict(self, data: dict) -> None:
        answers = data.get("answers", {}) or {}
        tooth_num = data.get("tooth_number")
        if tooth_num is not None:
            answers = dict(answers)
            answers["tooth_number"] = tooth_num
            data["answers"] = answers
        dx = generate_diagnosis_payload(answers, use_ai_fallback=True)
        self._apply_dx_result_dict(data, dx)

    def _apply_diagnosis_to_instance(self, instance: VisitHistory) -> None:
        ans = instance.answers or {}
        if instance.tooth_number is not None:
            ans = dict(ans)
            ans["tooth_number"] = instance.tooth_number
        dx = generate_diagnosis_payload(ans, use_ai_fallback=True) # type: ignore
        instance.results = clean_json(dx)
        instance.answers = clean_json(ans)

        # same mapping logic to top-level fields
        pulp = peri = etio = ""
        if isinstance(dx, dict) and dx.get("source") == "rules_engine":
            res = dx.get("results") or []
            if isinstance(res, list) and res and isinstance(res[0], dict):
                first = res[0]
                pulp = first.get("pulp_diagnosis", "") or ""
                peri = first.get("periapical_disease", "") or ""
                etio = first.get("etiology", "") or ""
        instance.pulp_diagnosis = pulp  # type: ignore
        instance.periapical_disease = peri  # type: ignore
        instance.etiology = etio  # type: ignore

    # ------------ create / update ------------
    def create(self, validated_data):
        # set doctor from request user if you want (optional):
        # validated_data['doctor'] = self.context['request'].user.doctor
        validated_data.pop("remove_tooth_image", None)
        self._apply_diagnosis_to_dict(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # forbid changing patient on an existing visit
        if "patient" in validated_data and validated_data["patient"].id != instance.patient_id:
            raise serializers.ValidationError({"patient": "Cannot change patient of an existing visit."})

        # optional image removal
        if validated_data.pop("remove_tooth_image", False):
            if instance.tooth_image:
                instance.tooth_image.delete(save=False)
            instance.tooth_image = None

        original_tooth_number = instance.tooth_number
        answers_changed = "answers" in validated_data
        tooth_number_changed = (
            "tooth_number" in validated_data
            and validated_data["tooth_number"] != original_tooth_number
        )
        instance = super().update(instance, validated_data)

        # recompute when inputs that influence diagnosis changed
        if answers_changed or tooth_number_changed:
            self._apply_diagnosis_to_instance(instance)
            instance.save(update_fields=["answers", "results", "pulp_diagnosis", "periapical_disease", "etiology"])

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
