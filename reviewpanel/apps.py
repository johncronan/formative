from django.apps import AppConfig


class ReviewPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reviewpanel'
    
    def ready(self):
        from . import signals
