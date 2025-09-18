# endo/views/auth.py
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from endo.models import Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory
from endo.permissions import IsVisitOwnerOrStaff
from endo.serializers import DoctorProfileSerializer, DoctorRegisterSerializer, EtiologyAvailabilityIn, NotificationReadStatusSerializer, NotificationSerializer, PatientSerializer, ResearchPaperSerializer, VisitHistorySerializer, diagnosis_engine
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

class RegisterDoctorView(APIView):
    def post(self, request):
        serializer = DoctorRegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Doctor registered successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not user.check_password(current_password):
            return Response({'detail': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({'detail': 'New passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'detail': 'New password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'detail': 'Account deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)

class DoctorProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = DoctorProfileSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = DoctorProfileSerializer(request.user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
    
    
class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self): # type: ignore
        return Patient.objects.filter(doctor=self.request.user)

    def get_serializer_context(self):
        # So the serializer can access the request.user
        return {'request': self.request}
    
    def perform_create(self, serializer):
        doctor = self.request.user
        patient_id = serializer.validated_data.get('patient_id')

        if not patient_id or str(patient_id).strip() == '':
            existing_count = Patient.objects.filter(doctor=doctor).count()
            new_number = existing_count + 1
            patient_id = f"D{doctor.id:04d}-P{new_number:06d}"  # type: ignore # keep old pattern

        serializer.save(doctor=doctor, patient_id=patient_id)
        
class EtiologyAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = EtiologyAvailabilityIn(data=request.data)
        ser.is_valid(raise_exception=True)

        page1 = ser.validated_data["answers"] # type: ignore
        engine = diagnosis_engine  # use this if you import a singleton

        choices = engine.etiology_choices_from_page1(page1)
        return Response(
            {"etiologies": choices, "ruleset_version": engine.version},
            status=200,
        )
    
class VisitHistoryViewSet(viewsets.ModelViewSet):
    queryset = VisitHistory.objects.all()
    serializer_class = VisitHistorySerializer
    permission_classes = [IsAuthenticated, IsVisitOwnerOrStaff]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):  # type: ignore
        queryset = VisitHistory.objects.filter(doctor=self.request.user)
        patient_id = self.request.query_params.get('patient') # type: ignore
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset

    def perform_create(self, serializer):
        patient = serializer.validated_data['patient']

        # block creating visits for other doctors' patients (unless staff)
        if not self.request.user.is_staff and patient.doctor_id != self.request.user.id: # type: ignore
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You can only create visits for your own patients.")

        visit_count = VisitHistory.objects.filter(patient=patient).count()
        new_case_number = visit_count + 1
        case_id = f"{patient.patient_id}-CID{new_case_number:07d}"

        serializer.save(doctor=self.request.user, case_id=case_id)
    
class ResearchPaperViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ResearchPaper.objects.all().order_by('-added_date')
    serializer_class = ResearchPaperSerializer
    permission_classes = [IsAuthenticated]
    
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

class NotificationReadStatusViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationReadStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self): # type: ignore
        return NotificationReadStatus.objects.filter(doctor=self.request.user).select_related('notification').order_by('-notification__created_at')

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user)