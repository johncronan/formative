from django.apps import AppConfig


class FormativeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'formative'
    
    def ready(self):
        from . import signals
