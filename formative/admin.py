from django import forms, urls
from django.contrib import admin, auth
from django.contrib.admin.views.main import ChangeList
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode
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
site.register(auth.models.Group, auth.admin.GroupAdmin)
site.register(auth.models.User, auth.admin.UserAdmin)

site.register(Program)


class FormChangeList(ChangeList):
    def url_for_result(self, result):
        pk = getattr(result, self.pk_attname)
        url = reverse('admin:%s_formblock_formlist' % (self.opts.app_label,),
                       args=(int(pk),),
                       current_app=self.model_admin.admin_site.name)
        return url


@admin.register(Form, site=site)
class FormAdmin(admin.ModelAdmin):
    list_display = ('name', 'program')
    list_filter = ('program',)
    fields = ('program', 'name', 'options', 'status')
    radio_fields = {'status': admin.VERTICAL}
    
    def get_changelist(self, request, **kwargs):
        return FormChangeList
    
    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if not obj: fields = tuple(f for f in fields if f != 'status')
        return fields
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'status' not in form.base_fields: return form
        
        choices = form.base_fields['status'].choices
        if obj and obj.status != Form.Status.DRAFT:
            form.base_fields['status'].choices = choices[1:]
        return form
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.status == Form.Status.DRAFT:
            fields = fields + ('status',)
        return fields
        
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
    
    def response_post_save_change(self, request, obj):
        app_label = self.model._meta.app_label
        url = reverse('admin:%s_formblock_formlist' % (app_label,),
                      args=(obj.id,), current_app=self.admin_site.name)
        return HttpResponseRedirect(url)


@admin.register(FormLabel, site=site)
class FormLabelAdmin(admin.ModelAdmin):
    list_display = ('path', 'style', 'form')
    list_filter = ('form',)
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield= super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'text':
            attrs = formfield.widget.attrs
            attrs['class'], attrs['cols'] = 'vTextArea', 60
            formfield.widget = forms.Textarea(attrs=attrs)
        return formfield


class FormDependencyInline(admin.TabularInline):
    model = FormDependency
    extra = 0
    verbose_name_plural = 'dependency values'


class FormBlockBase:
    # only methods that can be safely overridden in either parent or child admin
    
    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        fields.remove('dependence')
        fields.remove('negate_dependencies')
        
        main = (None, {'fields': fields})
        if not obj: return [main]
        return [main, ('Dependence', {'fields': ['dependence',
                                                 'negate_dependencies']})]
    
    def get_form(self, request, obj=None, **kwargs):
        form_id = request.GET.get('form_id')
        form = super().get_form(request, obj, **kwargs)
        
        if obj and form_id:
            qs = form.base_fields['dependence'].queryset
            qs = qs.filter(form_id=int(form_id), page__gt=0)
            qs = qs.exclude(pk=obj.pk).exclude(page__gte=obj.page)
            form.base_fields['dependence'].queryset = qs
        
        return form
    
    def get_formsets_with_inlines(self, request, obj=None):
        for inline in self.get_inline_instances(request, obj):
            # only show the inline on the change form, not add:
            if not isinstance(inline, FormDependencyInline) or obj is not None:
                yield inline.get_formset(request, obj), inline
    
    def response_post_save_change(self, request, obj):
        app_label = self.model._meta.app_label
        form_id = request.GET.get('form_id')
        
        if form_id:
            url = reverse('admin:%s_formblock_formlist' % (app_label,),
                          args=(form_id,), current_app=self.admin_site.name)
            return HttpResponseRedirect(url)
        
        return super().response_post_save_change(request, obj)
    
    def response_post_save_add(self, request, obj):
        if request.GET.get('form_id'):
            return self.response_post_save_change(request, obj)
        return super().response_post_save_add(request, obj)
    
    def save_form(self, request, form, change):
        form_id = request.GET.get('form_id')
        obj = form.save(commit=False)
        
        if form_id: obj.form_id = form_id
        return obj
    
    def changeform_view(self, request, object_id=None, form_url='', *args):
        form_id = request.GET.get('form_id')
        if form_id:
            form_arg = urlencode({'form_id': form_id})
            if form_url: form_url += '&' + form_arg
            else: form_url = '?' + form_arg
        
        return super().changeform_view(request, object_id, form_url, *args)
    
    def has_add_permission(self, request):
        match, app_label = request.resolver_match, self.model._meta.app_label
        # this will hide add button when we don't have the form_id
        if match and match.url_name == f'{app_label}_formblock_changelist':
            return False
        return super().has_add_permission(request)


class FormBlockAdminForm(forms.ModelForm):
    negate_dependencies = forms.BooleanField(label='Negate dependency',
                                             required=False)
    
    class Meta:
        model = FormBlock
        fields = ('name', 'page', 'dependence', 'negate_dependencies',
                  'options')


@admin.register(FormBlock, site=site)
class FormBlockAdmin(FormBlockBase, PolymorphicParentModelAdmin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_display = ('name', 'page') # 'polymorphic_ctype_id')
    list_filter = ('page',)
    form = FormBlockAdminForm
    inlines = [FormDependencyInline]
    
    def get_urls(self):
        urls = super().get_urls()
        
        url = path('form/<int:form_id>/', self.formlist_view,
                   name='%s_formblock_formlist' % (self.model._meta.app_label,))
        return [url] + urls
    
    def formlist_view(self, request, form_id, **kwargs):
        return self.changelist_view(request, extra_context={'form_id': form_id})
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        match, app_label = request.resolver_match, self.model._meta.app_label
        if match and match.url_name == f'{app_label}_formblock_formlist':
            return qs.filter(form_id=match.kwargs['form_id'])
        return qs
    
    def change_view(self, *args, **kwargs):
        # we still have use the bulk action for delete - it redirects properly
        kwargs['extra_context'] = {'show_delete': False}
        return super().change_view(*args, **kwargs)
    
    def get_preserved_filters(self, request):
        match, app_label = request.resolver_match, self.model._meta.app_label
        
        # we have to reimplement, because of our custom changelist view
        if self.preserve_filters and match:
            current_url = f'{match.app_name}:{match.url_name}'
            changelists = [ f'admin:{app_label}_formblock_{n}'
                            for n in ('formlist', 'changelist') ]
            if current_url in changelists: preserved = request.GET.urlencode()
            else: preserved = request.GET.get('_changelist_filters')
            
            args = {}
            if preserved: args['_changelist_filters'] = preserved
            if current_url == changelists[0]:
                args['form_id'] = match.kwargs['form_id']
            return urlencode(args)
        return ''


class FormBlockChildAdmin(FormBlockBase, PolymorphicChildModelAdmin):
    base_form = FormBlockAdminForm
    inlines = [FormDependencyInline]
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fieldsets[0][1]['fields'] += self.child_fields
        return fieldsets
            


@admin.register(CustomBlock, site=site)
class CustomBlockAdmin(FormBlockChildAdmin):
    base_model = FormBlock
    radio_fields = {'type': admin.VERTICAL}
    
    child_fields = ('type', 'required', 'num_lines',
                    'min_chars', 'max_chars', 'min_words', 'max_words')


@admin.register(CollectionBlock, site=site)
class CollectionBlockAdmin(FormBlockChildAdmin):
    base_model = FormBlock
    
    child_fields = ('fixed', 'min_items', 'max_items', 'has_file',
                    'file_optional', 'name1', 'name2', 'name3')


# TODO: ok to do this here if we check if setup has happened first
#for form in Form.objects.exclude(status=Form.Status.DRAFT):
#    site.register(form.model)
#    if form.item_model: site.register(form.item_model)
