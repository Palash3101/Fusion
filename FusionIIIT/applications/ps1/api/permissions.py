"""
permissions.py — Role-Based Access Control helpers for PS1 module
Metric 4: Security/RBAC
"""

import logging
from functools import wraps
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('ps1.permissions')

# ── Role constants (must match HoldsDesignation names in DB) ─────────────────

ROLE_PS_ADMIN = 'PS_Admin'
ROLE_DEPT_ADMIN = 'deptadmin'
ROLE_DEPT_HEAD = 'HOD'
ROLE_DIRECTOR = 'Director'
ROLE_REGISTRAR = 'Registrar'
ROLE_ACCOUNTS = 'Accounts_Admin'
ROLE_AUDITOR = 'Auditor'
ROLE_EMPLOYEE = 'Employee'

# Role groups for convenience
PROCUREMENT_ROLES = {ROLE_PS_ADMIN, ROLE_DEPT_ADMIN}
APPROVER_ROLES = {ROLE_DEPT_HEAD, ROLE_DIRECTOR, ROLE_REGISTRAR, ROLE_PS_ADMIN}
FINANCIAL_ROLES = {ROLE_ACCOUNTS, ROLE_AUDITOR}
ADMIN_ROLES = {ROLE_PS_ADMIN, ROLE_DIRECTOR, ROLE_REGISTRAR}


def get_user_roles(user):
    """Return set of designation names held by the user."""
    from applications.globals.models import HoldsDesignation
    return set(
        HoldsDesignation.objects
        .filter(user=user)
        .select_related('designation')
        .values_list('designation__name', flat=True)
    )


def has_any_role(user, allowed_roles):
    """Return True if the user holds at least one of the allowed roles."""
    return bool(get_user_roles(user) & set(allowed_roles))


def require_roles(*allowed_roles):
    """
    View decorator enforcing role-based access.
    Usage:
        @require_roles(ROLE_PS_ADMIN, ROLE_DEPT_ADMIN)
        def my_view(request, ...):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                logger.warning(
                    'Unauthenticated access attempt to %s', view_func.__name__
                )
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            if not has_any_role(request.user, allowed_roles):
                logger.warning(
                    'RBAC denied: user=%s view=%s required=%s',
                    request.user.username, view_func.__name__, allowed_roles
                )
                return Response(
                    {
                        'error': 'You do not have permission to perform this action.',
                        'required_roles': list(allowed_roles),
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def require_indent_owner_or_admin(view_func):
    """
    Allow only the indent owner or admins to access/modify the indent.
    Expects `indent_id` kwarg in the URL.
    """
    @wraps(view_func)
    def wrapped(request, indent_id=None, *args, **kwargs):
        from applications.ps1.models import IndentFile
        from django.shortcuts import get_object_or_404

        indent = get_object_or_404(IndentFile, pk=indent_id)
        is_owner = indent.file_info.uploader.user == request.user
        is_admin = has_any_role(request.user, ADMIN_ROLES | PROCUREMENT_ROLES)

        if not (is_owner or is_admin):
            logger.warning(
                'Ownership check failed: user=%s indent=%s',
                request.user.username, indent_id
            )
            return Response(
                {'error': 'You do not have access to this indent.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return view_func(request, indent_id=indent_id, *args, **kwargs)
    return wrapped
