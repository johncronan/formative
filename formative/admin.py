from django import forms, urls
from django.contrib import admin
from django.utils import timezone
from polymorphic.admin import (PolymorphicParentModelAdmin,
                               PolymorphicChildModelAdmin,
                               PolymorphicChildModelFilter)
import sys, importlib

from .models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock


class FormativeAdminSite(admin.AdminSite):
    def get_app_list(self, request):
        # unlike normal Django, we might have had changes to the admin urls
        urls.clear_url_caches()
        if 'urls' in sys.modules: importlib.reload(sys.modules['urls'])
        
        return super().get_app_list(request)


site = FormativeAdminSite()

site.register(Program)


@admin.register(Form, site=site)
class FormAdmin(admin.ModelAdmin):
    def response_change(self, request, obj):
        ret = super().response_change(request, obj)
        
        action, kwargs = None, {}
        if '_publish' in request.POST: action = 'publish'
        elif '_unpublish' in request.POST: action = 'unpublish'
        
        if obj.status == Form.Status.DRAFT:
            obj.modified = timezone.now()
        elif obj.status in (Form.Status.DISABLED, Form.Status.COMPLETED):
            obj.completed = timezone.now()
        else:
            obj.completed = None
        obj.save()
        
        if action:
            getattr(obj, action)(**kwargs)
        return ret


@admin.register(FormLabel, site=site)
class FormLabelAdmin(admin.ModelAdmin):
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield= super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'text':
            formfield.widget = forms.Textarea(attrs=formfield.widget.attrs)
        return formfield


site.register(FormDependency)


@admin.register(FormBlock, site=site)
class FormBlockAdmin(PolymorphicParentModelAdmin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_display = ('form', 'name', 'page', 'rank')
    list_filter = (PolymorphicChildModelFilter,)


@admin.register(CustomBlock, site=site)
class CustomBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock


@admin.register(CollectionBlock, site=site)
class CollectionBlockAdmin(PolymorphicChildModelAdmin):
    base_model = FormBlock


# TODO: ok to do this here if we check if setup has happened first
#for form in Form.objects.exclude(status=Form.Status.DRAFT):
#    site.register(form.model)
#    if form.item_model: site.register(form.item_model)
