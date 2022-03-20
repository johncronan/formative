from django.apps import AppConfig
from django.db.models import F, Value, CharField
from django.db.models.functions import Concat


class FormativeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'formative'
    
    def get_model(self, model_name, require_ready=True):
        model = None
        try: model = super().get_model(model_name, require_ready)
        except LookupError: pass
        if model or not require_ready or '_' not in model_name: return model
        
        from .models import Form
        part = model_name[:model_name.index('_')]
        queryset = Form.objects.filter(program__db_slug__startswith=part)
        name = Concat(F('program__db_slug'), Value('_'), F('db_slug'),
                      output_field=CharField())
        for form in queryset.annotate(n=name).filter(n=model_name):
            # accessing the models will register them for the call to super
            form.model, form.item_model
        
        return super().get_model(model_name)
            
    def ready(self):
        from . import signals
