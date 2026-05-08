from django.http import HttpResponseForbidden

from psmodule.selectors import get_extrainfo_for_user, has_designation


def get_user_depadmin_role(user):
    role = getattr(user, "role", "")
    if isinstance(role, str) and role.startswith("depadmin_"):
        return role

    try:
        extrainfo = get_extrainfo_for_user(user)
    except Exception:
        return None

    if not has_designation(extrainfo, "depadmin"):
        return None

    department_code = getattr(extrainfo.department, "code", "")
    if not isinstance(department_code, str) or not department_code:
        return None

    return f"depadmin_{department_code.lower()}"


def get_user_ps_admin_role(user):
    role = getattr(user, "role", "")
    if isinstance(role, str) and role == "PS_ADMIN":
        return role

    try:
        extrainfo = get_extrainfo_for_user(user)
    except Exception:
        return None

    if has_designation(extrainfo, "ps admin"):
        return "PS_ADMIN"

    return None


def get_ps_admin_role(request):
    return get_user_ps_admin_role(request.user)


def get_depadmin_department(request):
    depadmin_role = get_user_depadmin_role(request.user)
    if isinstance(depadmin_role, str) and depadmin_role.startswith("depadmin_"):
        return depadmin_role.replace("depadmin_", "dep_")
    return None


def require_depadmin_role(request):
    department = get_depadmin_department(request)
    if not department:
        return HttpResponseForbidden("Access Denied")
    return department
