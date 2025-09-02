# endo/permissions.py
from rest_framework.permissions import BasePermission

class IsVisitOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj): # type: ignore
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or getattr(user, "is_superuser", False):
            return True
        return obj.doctor_id == user.id
