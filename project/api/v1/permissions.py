from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

ADMIN = 0


class IsOwner(permissions.IsAuthenticated):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Instance must have an attribute named `user`.
        if hasattr(obj, 'user_id') and obj.user_id is not None:
            return obj.user_id == request.user.id

        if request.method in SAFE_METHODS:
            return True
        return False


# TODO: как-то причесать
class IsOwnerOrAdminRoles(permissions.IsAuthenticated):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Instance must have an attribute named `user`.
        if request.user.role in getattr(view, 'admin_roles'):
            return True

        if hasattr(obj, 'manager_id') and obj.user_id is not None:
            return obj.manager_id == request.user.id

        if hasattr(obj, 'user_id') and obj.user_id is not None:
            return obj.user_id == request.user.id

        if hasattr(obj, 'created_by_id') and obj.created_by_id is not None:
            return obj.created_by_id == request.user.id
        # if request.method in SAFE_METHODS:
        #     return True
        return False


class AllowedRoles(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            if not hasattr(view, 'allowed_roles'):
                return True
            elif request.user.role in getattr(view, 'allowed_roles'):  # or request.user.is_superuser:
                return True
        return False
