# endo/views/auth.py
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from endo.models import Notification, NotificationReadStatus, Patient, ResearchPaper, VisitHistory
from endo.serializers import DoctorProfileSerializer, DoctorRegisterSerializer, NotificationReadStatusSerializer, NotificationSerializer, PatientSerializer, ResearchPaperSerializer, VisitHistorySerializer
from rest_framework.permissions import IsAuthenticated

class RegisterDoctorView(APIView):
    def post(self, request):
        serializer = DoctorRegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Doctor registered successfully."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    
class VisitHistoryViewSet(viewsets.ModelViewSet):
    queryset = VisitHistory.objects.all()
    serializer_class = VisitHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):  # type: ignore
        queryset = VisitHistory.objects.filter(doctor=self.request.user)
        patient_id = self.request.query_params.get('patient') # type: ignore
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset
    
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