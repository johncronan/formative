from django import forms
from django.contrib import admin
from polymorphic.admin import (PolymorphicParentModelAdmin,
                               PolymorphicChildModelAdmin,
                               PolymorphicChildModelFilter)

from .models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock

admin.site.register(Program)

@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    def response_change(self, request, obj):
        ret = super().response_change(request, obj)
        
        action, kwargs = None, {}
        if '_publish' in request.POST: action = 'publish'
        elif '_unpublish' in request.POST: action = 'unpublish'
        
        if action:
            getattr(obj, action)(**kwargs)
        return ret

@admin.register(FormLabel)
class FormLabelAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield= super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'text':
            formfield.widget = forms.Textarea(attrs=formfield.widget.attrs)
        return formfield

admin.site.register(FormDependency)

@admin.register(FormBlock)
class FormBlockAdmin(PolymorphicParentModelAdmin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_filter = (PolymorphicChildModelFilter,)

@admin.register(CustomBlock)
class CustomBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock

@admin.register(CollectionBlock)
class CollectionBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock

# TODO: ok to do this here if we check if setup has happened first
#for form in Form.objects.exclude(status=Form.Status.DRAFT):
#    class SubmissionAdmin(admin.ModelAdmin):
#        pass
#    admin.site.register(form.model, SubmissionAdmin)
