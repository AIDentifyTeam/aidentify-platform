# endo/urls.py
from django.urls import path, include
from endo.views import ChangePasswordView, DeleteAccountView, DoctorProfileView, EtiologyAvailabilityView, LogoutView, NotificationReadStatusViewSet, NotificationViewSet, RegisterDoctorView, PatientViewSet, ResearchPaperViewSet, VisitHistoryViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'visits', VisitHistoryViewSet, basename='visithistory')
router.register(r'research-papers', ResearchPaperViewSet, basename='researchpaper')
router.register('notifications', NotificationViewSet, basename='notification')
router.register('notification-status', NotificationReadStatusViewSet, basename='notification-status')

urlpatterns = [
    path("etiologies/", EtiologyAvailabilityView.as_view()),
    path('register/', RegisterDoctorView.as_view(), name='register'),
    path('profile/', DoctorProfileView.as_view(), name='doctor-profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('delete-account/', DeleteAccountView.as_view(), name='delete-account'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', include(router.urls)),
]
