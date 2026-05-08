from django.apps import AppConfig


class PsModuleConfig(AppConfig):
    """Procurement / indents app; lives at package root ``psmodule``."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "psmodule"
    label = "ps"
