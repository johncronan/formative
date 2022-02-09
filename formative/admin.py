from django import forms, urls
from django.contrib import admin, auth
from django.contrib.admin.views.main import ChangeList
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode
from django_better_admin_arrayfield.admin.mixins import DynamicArrayMixin
from polymorphic.admin import (PolymorphicParentModelAdmin,
                               PolymorphicChildModelAdmin,
                               PolymorphicChildModelFilter)
import sys, importlib
from urllib.parse import unquote, parse_qsl

from .forms import ProgramAdminForm, StockBlockAdminForm, \
    CustomBlockAdminForm, CollectionBlockAdminForm
from .models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock
from .signals import register_program_settings


class FormativeAdminSite(admin.AdminSite):
    def get_app_list(self, request):
        # unlike normal Django, we might have had changes to the admin urls
        urls.clear_url_caches()
        if 'urls' in sys.modules: importlib.reload(sys.modules['urls'])
        
        return super().get_app_list(request)


site = FormativeAdminSite()

site.register(auth.models.Group, auth.admin.GroupAdmin)
site.register(auth.models.User, auth.admin.UserAdmin)


@admin.register(Program, site=site)
class ProgramAdmin(admin.ModelAdmin, DynamicArrayMixin):
    list_display = ('name', 'created')
    form = ProgramAdminForm
    
    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        
        main = (None, {'fields': fields})
        if not obj: return [main]
        
        responses = register_program_settings.send(self)
        admin_fields = { k: v for _, r in responses for k, v in r.items() }
        if not admin_fields: return [main]
        return [
            main,
            ('Options', {'fields': list(admin_fields)}),
        ]


class FormChangeList(ChangeList):
    def url_for_result(self, result):
        pk = getattr(result, self.pk_attname)
        url = reverse('admin:%s_formblock_formlist' % (self.opts.app_label,),
                       args=(int(pk),),
                       current_app=self.model_admin.admin_site.name)
        return url


@admin.register(Form, site=site)
class FormAdmin(admin.ModelAdmin):
    list_display = ('name', 'program', 'created', 'modified')
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
        if obj:
            if obj.status == Form.Status.DRAFT: fields += ('status',)
            else: fields += ('program', 'name')
        return fields
        
    def response_change(self, request, obj):
        subs = []
        if obj.status != Form.Status.DRAFT:
            qs = obj.model.objects.all()
            if obj.item_model: qs = qs.annotate(num_items=Count('_item'))
            subs = qs.values_list('_email', 'num_items')
        
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'media': self.media,
            'object': obj,
            'submissions': subs,
        }
#        if '_publish' in request.POST:
#            return TemplateResponse(request, 'admin/publish_confirmation.html',
#                                    context)
        if '_unpublish' in request.POST:
            template_name = 'admin/formative/unpublish_confirmation.html'
            return TemplateResponse(request, template_name, context)
        
        action, kwargs = None, {}
        if '_publish' in request.POST: action = 'publish'
        elif '_unpublish_confirmed' in request.POST: action = 'unpublish'
        
        if not action: ret = super().response_change(request, obj)
        
        if obj.status == Form.Status.DRAFT:
            obj.modified = timezone.now()
        elif obj.status in (Form.Status.DISABLED, Form.Status.COMPLETED):
            obj.completed = timezone.now()
        else:
            obj.completed = None
        obj.save()
        
        if action:
            getattr(obj, action)(**kwargs)
            return HttpResponseRedirect(request.path)
        
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
    
    def has_add_permission(self, request, obj):
        if not obj: return False
        
        return obj.form.status == Form.Status.DRAFT
    
    def has_change_permission(self, request, obj):
        return self.has_add_permission(request, obj)
    
    def has_delete_permission(self, request, obj):
        return self.has_add_permission(request, obj)


@admin.action(description='Move to different page')
def move_blocks(modeladmin, request, queryset):
    pass # TODO


class FormBlockBase:
    # only methods that can be safely overridden in either parent or child admin
    
    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        fields.remove('dependence')
        fields.remove('negate_dependencies')
        fields.remove('no_review')
        
        main = (None, {'fields': fields})
        if not obj: return [main]
        return [
            main,
            ('Options', {'fields': ['no_review']}),
            ('Dependence', {'fields': ['dependence', 'negate_dependencies']})
        ]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj and obj.form.status != Form.Status.DRAFT:
            fields += ('name', 'page', 'dependence', 'negate_dependencies')
        elif obj: fields += ('page',)
        
        return fields
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        if obj and obj.form.status == Form.Status.DRAFT:
            # TODO: where would we modify form.fields instead?
            if 'dependence' in form.base_fields:
                qs = form.base_fields['dependence'].queryset
                qs = qs.filter(form=obj.form, page__gt=0)
                qs = qs.exclude(pk=obj.pk).exclude(page__gte=obj.page)
                form.base_fields['dependence'].queryset = qs
        
        return form
    
    def get_changeform_initial_data(self, request):
        changelist_filters = request.GET.get('_changelist_filters')
        if changelist_filters:
            filters = dict(parse_qsl(unquote(changelist_filters)))
            if 'page' in filters:
                return {'page': filters['page']}
        
        return {}
    
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
            changelist_filters = request.GET.get('_changelist_filters')
            if changelist_filters:
                filters = dict(parse_qsl(unquote(changelist_filters)))
                url = url + '?' + urlencode(filters)
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
    
    def try_form_id(self, request, match):
        form = None
        if 'form_id' in match.kwargs: pk = match.kwargs['form_id']
        else: pk = request.GET.get('form_id')
        if not pk: return form
        
        try: form = Form.objects.get(pk=pk)
        except Form.DoesNotExist: pass
        return form
    
    def has_add_permission(self, request):
        match, app_label = request.resolver_match, self.model._meta.app_label
        # this will hide add button when we don't have the form_id
        if match and match.url_name == f'{app_label}_formblock_changelist':
            return False
        # or when the form is not a draft
        pages = (f'{app_label}_formblock_{n}' for n in ('formlist', 'change'))
        if match and match.url_name in pages:
            form = self.try_form_id(request, match)
            if form and form.status != Form.Status.DRAFT: return False
        
        return super().has_add_permission(request)
    
    def has_delete_permission(self, request, obj=None):
        return self.has_add_permission(request)


@admin.register(FormBlock, site=site)
class FormBlockAdmin(FormBlockBase, PolymorphicParentModelAdmin,
                     DynamicArrayMixin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_display = ('name', 'page', 'labels_link')
    list_filter = ('page',)
    form = StockBlockAdminForm
    inlines = [FormDependencyInline]
    actions = [move_blocks]
    
    @admin.display(description='labels')
    def labels_link(self, obj):
        app_label = self.model._meta.app_label
        url = reverse('admin:%s_formlabel_changelist' % (app_label,),
                      current_app=self.admin_site.name)
        url += f'?form__id__exact={obj.form.pk}&path__startswith={obj.name}'
        return format_html('<a href="{}">{} labels</a>', url, obj.num_labels)
    
    @admin.display(description='type')
    def type(self, obj):
        # read-only version of the StockBlockAdminForm type field
        return obj.options['type']
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = fieldsets[0][1]['fields']
        
        if not obj: return fieldsets
        
        options = fieldsets[1][1]['fields']
        admin_fields = obj.stock.admin_fields().keys()
        options += [ f for f in admin_fields if f != 'choices' ]
        # special case: not really an option, so it goes on the general tab
        if 'choices' in admin_fields: fields.append('choices')
        
        sets = [(None, {'fields': fields}), ('Options', {'fields': options})] 
        return sets + fieldsets[2:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj: fields += ('type',)
        
        
        return fields
    
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
            qs = qs.filter(form_id=match.kwargs['form_id'])
        
        path_filter = Q(form__label__path__startswith=F('name'))
        qs = qs.annotate(num_labels=Count('form__label', filter=path_filter))
        return qs
    
    def change_view(self, *args, **kwargs):
        # we still have the bulk action for delete - it redirects properly
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
    base_model = FormBlock
    inlines = [FormDependencyInline]


@admin.register(CustomBlock, site=site)
class CustomBlockAdmin(FormBlockChildAdmin, DynamicArrayMixin):
    form = CustomBlockAdminForm
    radio_fields = {'type': admin.VERTICAL}
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = fieldsets[0][1]['fields']
        names = ['type', 'required', 'num_lines', 'min_chars', 'max_chars',
                 'min_words', 'max_words']
        
        if not obj: add = names[:1]
        elif obj.type == CustomBlock.InputType.TEXT: add = names[:1] + names[2:]
        elif obj.type == CustomBlock.InputType.BOOLEAN: add = names[:1]
        elif obj.type == CustomBlock.InputType.CHOICE:
            add = names[:2] + ['choices']
        else: add = names[:2]
        
        names.append('choices')
        ret = [ f for f in fields if f not in names ] + add
        return [(None, {'fields': ret})] + fieldsets[1:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj: fields += ('type',)
        if obj and obj.form.status != Form.Status.DRAFT:
            if obj.type == CustomBlock.InputType.TEXT:
                fields += ('num_lines', 'min_chars', 'max_chars')
            elif obj.type != CustomBlock.InputType.BOOLEAN:
                fields += ('required',)
        return fields


@admin.register(CollectionBlock, site=site)
class CollectionBlockAdmin(FormBlockChildAdmin):
    form = CollectionBlockAdminForm
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = fieldsets[0][1]['fields']
        names = ['fixed', 'name1', 'name2', 'name3', 'has_file',
                 'min_items', 'max_items', 'file_optional']
        
        if not obj: add = names[:5]
        elif obj.fixed: add = names[:4]
        elif not obj.has_file: add = names[:6]
        else: add = names[:]
        
        ret = [ f for f in fields if f not in names ] + add
        return [(None, {'fields': ret})] + fieldsets[1:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj: fields += ('fixed', 'has_file')
        if obj and obj.form.status != Form.Status.DRAFT:
            fields += ('name1', 'name2', 'name3')
        
        return fields


# TODO: ok to do this here if we check if setup has happened first
#for form in Form.objects.exclude(status=Form.Status.DRAFT):
#    site.register(form.model)
#    if form.item_model: site.register(form.item_model)
