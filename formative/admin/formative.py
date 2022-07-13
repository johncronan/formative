from django import forms
from django.contrib import admin, auth, sites
from django.contrib.admin.views.main import ChangeList
from django.db import connection
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse, NoReverseMatch
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django_better_admin_arrayfield.admin.mixins import DynamicArrayMixin
from polymorphic.admin import (PolymorphicParentModelAdmin,
                               PolymorphicChildModelAdmin,
                               PolymorphicChildModelFilter)
import types
from functools import partial
from urllib.parse import unquote, parse_qsl

from ..forms import ProgramAdminForm, FormAdminForm, DependencyAdminForm, \
    StockBlockAdminForm, CustomBlockAdminForm, CollectionBlockAdminForm, \
    SubmissionAdminForm, SubmissionItemAdminForm, SiteAdminForm, \
    UserCreationAdminForm
from ..models import Program, Form, FormLabel, FormBlock, FormDependency, \
    CustomBlock, CollectionBlock, SubmissionRecord, Site
from ..filetype import FileType
from ..plugins import get_matching_plugin
from ..signals import register_program_settings, register_form_settings, \
    register_user_actions, form_published_changed, form_settings_changed
from ..tasks import timed_complete_form
from ..utils import submission_link, get_current_site, user_programs
from .actions import UserActionsMixin, FormActionsMixin,FormBlockActionsMixin, \
    SubmissionActionsMixin, download_view


class FormativeAdminSite(admin.AdminSite):
    def __init__(self, *args, **kwargs):
        self.submissions_registered = None
        super().__init__(*args, **kwargs)
    
    def register_submission_models(self):
        for model in self.submissions_registered or {}:
            self.unregister(model)
        self.submissions_registered = {}
        
        if Form._meta.db_table in connection.introspection.table_names():
            for form in Form.objects.exclude(status=Form.Status.DRAFT):
                self.register(form.model, SubmissionAdmin)
                self.submissions_registered[form.model] = True
                
                if form.item_model:
                    self.register(form.item_model, SubmissionItemAdmin)
                    self.submissions_registered[form.item_model] = True
        
        form_published_changed.send(self)
    
    def get_urls(self):
        urls = super().get_urls()
        url = path('files_download/<int:form_id>/',
                   self.admin_view(download_view),
                   name='formative_files_download')
        return [url] + urls


site = FormativeAdminSite()

site.register(auth.models.Group, auth.admin.GroupAdmin)


@admin.register(auth.get_user_model(), site=site)
class UserAdmin(UserActionsMixin, auth.admin.UserAdmin):
    change_list_template = 'admin/formative/user/change_list.html'
    actions = ['make_active', 'make_inactive', 'send_password_reset']
    add_form = UserCreationAdminForm
    add_fieldsets = ((None, {'classes': ('wide',),
                             'fields': ('email', 'password1', 'password2',
                                        'is_staff')}),)
    
    def get_queryset(self, request):
        queryset, user = super().get_queryset(request), request.user
        
        if user.site: queryset = queryset.filter(site=user.site)
        if not user.is_superuser:
            queryset = queryset.filter(Q(is_staff=False) | Q(pk=user.pk))
        return queryset
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not obj: return fieldsets
        
        if obj.is_staff:
            main = ((None, {'fields': ('username', 'password', 'programs')}),)
        else: main = ((None, {'fields': ('email', 'password')}),)
        if request.user.is_superuser and not request.user.site:
            main = ((None, {'fields': main[0][1]['fields'] + ('site',)}),)
        
        info = ((fieldsets[1][0], {
            'fields': tuple(f for f in fieldsets[1][1]['fields']
                            if obj.is_staff or f != 'email')
        }),)
        return main + info + fieldsets[2:]
    
    def get_list_display(self, request):
        display = super().get_list_display(request)
        keep = tuple(f for f in display if f not in ('email', 'username'))
        if not request.user.is_superuser or request.user.site:
            return ('user_id',) + keep + ('is_active', 'date_joined')
        return ('user_id',) + keep + ('is_active', 'date_joined', 'site')
    
    def get_list_filter(self, request):
        filters = super().get_list_filter(request)
        if request.user.is_superuser and not request.user.site:
            return filters + ('site',)
        return filters
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not obj or not obj.is_staff:
            form.base_fields['email'].required = True
        
        if 'programs' not in form.base_fields: return form
        qs = form.base_fields['programs'].queryset
        site = get_current_site(request)
        if site: form.base_fields['programs'].queryset = qs.filter(sites=site)
        return form
    
    def has_change_permission(self, request, obj=None):
        if not request.user.is_superuser and obj and obj.is_staff:
            if obj.pk != request.user.pk: return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser and obj and obj.is_staff: return False
        return super().has_delete_permission(request, obj)
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser and obj:
            ro = ('programs', 'is_staff', 'is_superuser',
                  'groups', 'user_permissions')
            if obj.is_staff: ro = ('password',) + ro
            return ro + fields
        return fields
    
    def save_model(self, request, obj, form, change):
        # TODO need a username form field that strips out __{obj.site_id}
        site = get_current_site(request)
        if not obj.is_staff or not request.user.is_superuser: obj.site = site
        if request.user.is_superuser and request.user.site:
            obj.site = request.user.site
        # currently, this doesn't keep it updated when ID set, then changes
        if not obj.is_staff: obj.username = obj.email
        if obj.site and '__' not in obj.username:
            obj.username += f'__{obj.site_id}'
        super().save_model(request, obj, form, change)
    
    @admin.display(description='username')
    def user_id(self, obj):
        if obj.is_staff: return obj.username
        return obj.email # we hide the __{site_id} username from regular admins
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        
        responses = register_user_actions.send(self)
        plugin_actions = { k: v for _, r in responses for k, v in r.items() }
        for name, func in plugin_actions.items():
            func.__name__ = name
            actions[name] = self.get_action(func)
        return actions
    
    def make_active_ornot(self, request, qs, active=True):
        for obj in qs:
            obj.is_active = active
            obj.save()
        self.message_user(request, 'User status changed.')
    def make_active(self, request, queryset):
        return self.make_active_ornot(request, queryset)
    def make_inactive(self, request, queryset):
        return self.make_active_ornot(request, queryset, active=False)


@admin.register(Program, site=site)
class ProgramAdmin(admin.ModelAdmin, DynamicArrayMixin):
    list_display = ('name', 'created')
    form = ProgramAdminForm
    
    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        
        exclude = []
        if not request.user.is_superuser or request.user.site:
            exclude.append('sites')
        
        main = (None, {'fields': [ f for f in fields if f not in exclude ] })
        if not obj: return [main]
        
        responses = register_program_settings.send(self)
        admin_fields = { k: v for _, r in responses for k, v in r.items() }
        if not admin_fields: return [main]
        return [
            main,
            ('Options', {'fields': list(admin_fields)}),
        ]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj: fields += ('slug',)
        return fields
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        site = get_current_site(request)
        if not request.user.is_superuser and not request.user.site:
            queryset = queryset.filter(sites=site)
        return user_programs(queryset, '', request)
    
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        site = get_current_site(request)
        if site and request.user.is_superuser:
            initial['sites'] = (get_current_site(request),)
        return initial
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change and not request.user.is_superuser:
            site = get_current_site(request)
            if site: obj.sites.add(site)


class FormChangeList(ChangeList):
    def url_for_result(self, result):
        pk = getattr(result, self.pk_attname)
        url = reverse('admin:%s_formblock_formlist' % (self.opts.app_label,),
                       args=(int(pk),),
                       current_app=self.model_admin.admin_site.name)
        return url + '?page=1'


@admin.register(Form, site=site)
class FormAdmin(FormActionsMixin, admin.ModelAdmin):
    list_display = ('name', 'program', 'created', 'modified')
    list_filter = ('program',)
    form = FormAdminForm
    actions = ['form_plugins', 'export_json', 'duplicate']
    
    def get_changelist(self, request, **kwargs):
        return FormChangeList
    
    def get_fieldsets(self, request, obj=None):
        opt_fields = super().get_fields(request, obj)
        main_fields = ['program', 'name', 'slug', 'status', 'hidden']
        
        main = (None, {'fields': main_fields[:3] + main_fields[4:]})
        if not obj: return [main]
        
        for n in main_fields: opt_fields.remove(n)
        main[1]['fields'] = main_fields
        
        email_fields = ['email_names', 'emails']
        ret = [
            main,
            ('Options', {'fields': opt_fields}),
            ('Emails', {'fields': email_fields})
        ]
        responses = register_form_settings.send(obj)
        for receiver, response in responses:
            meta = get_matching_plugin(receiver.__module__)
            ret.append((meta.name, {'fields': list(response)}))
        return ret
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj:
            fields += ('plugins',)
            if obj.status == Form.Status.DRAFT: fields += ('status',)
            else: fields += ('program', 'slug')
        return fields
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        site = get_current_site(request)
        if site: queryset = queryset.filter(program__sites=site)
        return user_programs(queryset, 'program__', request)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        if 'program' not in form.base_fields: return form
        qs = form.base_fields['program'].queryset
        site = get_current_site(request)
        if site:
            qs = user_programs(qs.filter(sites=site), '', request)
            form.base_fields['program'].queryset = qs
        return form
    
    def save_form(self, request, form, change):
        obj = super().save_form(request, form, change)
        if not change: return obj
        
        if obj.status == Form.Status.DRAFT:
            obj.modified = timezone.now()
        elif obj.status in (Form.Status.DISABLED, Form.Status.COMPLETED):
            if 'status' in form.changed_data: obj.completed = timezone.now()
        else: obj.completed = None
        
        if 'email_names' in form.cleaned_data:
            names = []
            for n in form.cleaned_data['email_names'].split(','):
                name = n.strip()
                if not name: continue
                names.append(name)
                if name not in obj.emails():
                    if 'emails' not in obj.options: obj.options['emails'] = {}
                    obj.options['emails'][name] = {'subject': '', 'content': ''}
            for name in obj.email_names():
                if name in ('continue', 'confirmation'): continue
                if name not in names: del obj.options['emails'][name]
            if 'emails' in obj.options and not obj.options['emails']:
                del obj.options['emails']
        
        if 'timed_completion' in form.changed_data:
            val = form.cleaned_data['timed_completion']
            timed_complete_form.apply_async(args=(obj.id, val), eta=val)
        
        return obj
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        form_settings_changed.send(obj, changed_data=form.changed_data)
    
    def response_post_save_change(self, request, obj):
        app_label = self.model._meta.app_label
        url = reverse('admin:%s_formblock_formlist' % (app_label,),
                      args=(obj.id,), current_app=self.admin_site.name)
        return HttpResponseRedirect(url)
    
    def has_delete_permission(self, request, obj=None):
        if obj and obj.status != Form.Status.DRAFT: return False
        return super().has_delete_permission(request, obj)
    
    def plugins(self, obj):
        return ', '.join(obj.get_plugins()) or None


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
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        site = get_current_site(request)
        qs = form.base_fields['form'].queryset.filter(program__sites=site)
        form.base_fields['form'].queryset = user_programs(qs, 'program__',
                                                          request)
        return form
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        site = get_current_site(request)
        return user_programs(queryset.filter(form__program__sites=site),
                             'form__program__', request)


class FormDependencyFormSet(forms.BaseInlineFormSet):
    def __init__(self, dependence=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dependence = dependence
    
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['dependence'] = self.dependence
        return kwargs

class FormDependencyInline(admin.TabularInline):
    model = FormDependency
    extra = 0
    formset = FormDependencyFormSet
    form = DependencyAdminForm
    verbose_name_plural = 'dependency values'
    
    def has_add_permission(self, request, obj):
        if not obj: return False
        
        return obj.form.status == Form.Status.DRAFT
    
    def has_change_permission(self, request, obj=None):
        return self.has_add_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        return self.has_add_permission(request, obj)


class FormBlockBase:
    # only methods that can be safely overridden in either parent or child admin
    
    def get_fieldsets(self, request, obj=None):
        fields = list(dict.fromkeys(self.get_fields(request, obj)))
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
        
        form_id = request.GET.get('form_id')
        if form_id: form.form_id = form_id
        
        if obj and obj.form.status == Form.Status.DRAFT:
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
    
    def get_formset_kwargs(self, request, obj=None, *args):
        kwargs = super().get_formset_kwargs(request, obj, *args)
        if obj: kwargs['dependence'] = obj.dependence
        return kwargs
        
    def get_formsets_with_inlines(self, request, obj=None):
        for inline in self.get_inline_instances(request, obj):
            # only show the inline on the change form, not add:
            if not isinstance(inline, FormDependencyInline) or obj is not None:
                yield inline.get_formset(request, obj), inline
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        site = get_current_site(request)
        return user_programs(qs.filter(form__program__sites=site),
                             'form__program__', request)
        
    def response_add(self, request, obj, **kwargs):
        if '_popup' in request.POST or '_continue' not in request.POST:
            return super().response_add(request, obj, **kwargs)
        
        opts = obj._meta
        model = opts.model_name
        if model in ('customblock', 'collectionblock'): model = 'formblock'
        url = reverse('admin:%s_%s_change' % (opts.app_label, model),
                      args=(obj.pk,), current_app=self.admin_site.name)
        
        preserved, args = request.GET.get('_changelist_filters'), {}
        if preserved: args['_changelist_filters'] = preserved
        args['form_id'] = obj.form.id
        url += '?' + urlencode(args)
        
        if 'get_url' in kwargs: return url
        return super().response_add(request, obj, post_url_continue=url)
    
    def response_change(self, request, obj):
        if '_popup' in request.POST or '_continue' not in request.POST:
            return super().response_change(request, obj)
        
        url = self.response_add(request, obj, get_url=True)
        return HttpResponseRedirect(url)
    
    def response_post_save_change(self, request, obj):
        app_label = self.model._meta.app_label
        form_id = request.GET.get('form_id')
        
        if not obj and not form_id:
            return super().response_post_save_change(request, obj)
        
        if not form_id: form_id = obj.form.id
        url = reverse('admin:%s_formblock_formlist' % (app_label,),
                      args=(form_id,), current_app=self.admin_site.name)
        changelist_filters = request.GET.get('_changelist_filters')
        if changelist_filters:
            filters = dict(parse_qsl(unquote(changelist_filters)))
            url += '?' + urlencode(filters)
        return HttpResponseRedirect(url)
    
    def response_post_save_add(self, request, obj):
        if request.GET.get('form_id'):
            return self.response_post_save_change(request, obj)
        return super().response_post_save_add(request, obj)
    
    def changeform_view(self, request, object_id=None, form_url='',
                        extra_context=None):
        form_id = request.GET.get('form_id')
        if form_id:
            form_arg = urlencode({'form_id': form_id})
            if form_url: form_url += '&' + form_arg
            else: form_url = '?' + form_arg
            
            if not extra_context: extra_context = {}
            name = get_object_or_404(Form, id=int(form_id)).name
            extra_context.update({'form_id': int(form_id), 'form_name': name})
            
            initial = self.get_changeform_initial_data(request)
            if 'page' in initial: extra_context['page'] = initial['page']
            else: extra_context['page'] = None
        
        return super().changeform_view(request, object_id, form_url,
                                       extra_context)
    
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
        match = request.resolver_match
        if 'form_id' not in match.kwargs:
            return self.has_add_permission(request)
        
        try: form = Form.objects.get(id=match.kwargs['form_id'])
        except Form.DoesNotExist: return False
        if form.status != Form.Status.DRAFT: return False
        page = request.GET.get('page')
        if page is None or not page.isdigit(): page = None
        if page and not int(page): return False
        return True


class PageListFilter(admin.SimpleListFilter):
    title = 'page'
    parameter_name = 'page'
    template = 'admin/formative/formblock/filter.html'
    
    def lookups(self, request, model_admin):
        qs = model_admin.get_queryset(request).distinct().order_by('page')
        ret = list(qs.values_list('page', flat=True))
        if len(ret) == 1: ret.append(1)
        return [ (p, f'Page {p}' if p else 'Auto-created blocks') for p in ret ]
    
    def queryset(self, request, queryset):
        val = self.value()
        if val is None: return queryset
        if not val.isdigit(): return queryset.none()
        return queryset.filter(page=self.value())


@admin.register(FormBlock, site=site)
class FormBlockAdmin(FormBlockActionsMixin, FormBlockBase,
                     PolymorphicParentModelAdmin, DynamicArrayMixin):
    child_models = (FormBlock, CustomBlock, CollectionBlock)
    list_display = ('_rank', 'name', 'block_type', 'dependence', 'labels_link')
    list_display_links = ('name',)
    list_editable = ('_rank',)
    list_filter = (PageListFilter,)
    form = StockBlockAdminForm
    inlines = [FormDependencyInline]
    actions = ['move_blocks_action']
    sortable_by = ()
    polymorphic_list = True
    
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
        readonly_fields = obj.stock.admin_published_readonly()
        if obj.form.status == Form.Status.DRAFT:
            # special case: not really an option, so it goes on the general tab
            if 'choices' in admin_fields: fields.append('choices')
            options += [ f for f in admin_fields if f != 'choices' ]
        else:
            options += [ f for f in admin_fields if f not in readonly_fields ]
        
        sets = [(None, {'fields': fields}), ('Options', {'fields': options})] 
        return sets + fieldsets[2:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if not obj: return fields
        fields += ('type',)
        
        if obj.form.status != Form.Status.DRAFT:
            for field, label in obj.stock.admin_published_readonly().items():
                def field_callable(f, l):
                    @admin.display(description=l)
                    def callable(self, obj):
                        if f not in obj.options: return '-'
                        return obj.options[f]
                    return callable
                
                setattr(self, field,
                        types.MethodType(field_callable(field, label), self))
                fields += (field,)
        
        return fields
    
    def get_urls(self):
        urls = super().get_urls()
        
        url = path('form/<int:form_id>/', self.formlist_view,
                   name='%s_formblock_formlist' % (self.model._meta.app_label,))
        return [url] + urls
    
    def formlist_view(self, request, form_id, **kwargs):
        page = request.GET.get('page')
        if not page: return HttpResponseRedirect(request.path + '?page=1')
        
        name = get_object_or_404(Form, id=int(form_id)).name
        context = {'form_id': form_id, 'form_name': name}
        return self.changelist_view(request, extra_context=context)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        match, app_label = request.resolver_match, self.model._meta.app_label
        if match and match.url_name == f'{app_label}_formblock_formlist':
            qs = qs.filter(form_id=match.kwargs['form_id'])
        
        path_filter = Q(form__label__path__startswith=F('name'))
        qs = qs.annotate(num_labels=Count('form__label', filter=path_filter))
        return qs
    
    def get_changelist_form(self, request, **kwargs):
        page = request.GET.get('page')
        if page is None or not page.isdigit(): page = None
        
        class HiddenWithHandleInput(forms.HiddenInput):
            template_name = 'admin/formative/widgets/hidden_with_handle.html'
        
        if 'form_id' in request.resolver_match.kwargs and page and int(page):
            kwargs['widgets'] = {'_rank': HiddenWithHandleInput}
        else: kwargs['widgets'] = {'_rank': forms.HiddenInput}
        return super().get_changelist_form(request, **kwargs)
    
    def add_view(self, *args, **kwargs):
        kwargs['extra_context'] = {'show_save_and_add_another': False}
        return super().add_view(*args, **kwargs)
    
    def change_view(self, *args, **kwargs):
        # we still have the bulk action for delete - it redirects properly
        kwargs['extra_context'] = {'show_delete': False,
                                   'show_save_and_add_another': False}
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
    
    def choices(self, obj):
        return obj.options['choices']
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = fieldsets[0][1]['fields']
        names = ['type', 'required', 'num_lines', 'min_chars', 'max_chars',
                 'min_words', 'max_words']
        
        if not obj:
            return [(None, {'fields': ['name', 'page', 'type']})]
        
        options = fieldsets[1][1]['fields']
        if obj.type == CustomBlock.InputType.TEXT: add = names[:1] + names[2:]
        elif obj.dependence: options.append('default_value')
        if obj.type == CustomBlock.InputType.BOOLEAN: add = names[:1]
        elif obj.type == CustomBlock.InputType.CHOICE:
            add = names[:2] + ['choices']
        elif obj.type == CustomBlock.InputType.NUMERIC:
            add = names[:2]
            options += ['numeric_min', 'numeric_max']
        
        names += ['choices', 'numeric_min', 'numeric_max', 'default_value']
        main = [ f for f in fields if f not in names ] + add
        
        sets = [(None, {'fields': main}), ('Options', {'fields': options})]
        return sets + fieldsets[2:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj: fields += ('type',)
        if obj and obj.form.status != Form.Status.DRAFT:
            if obj.type == CustomBlock.InputType.TEXT:
                fields += ('num_lines', 'max_chars')
            elif obj.type == CustomBlock.InputType.CHOICE:
                fields += ('choices',)
        return fields


@admin.register(CollectionBlock, site=site)
class CollectionBlockAdmin(FormBlockChildAdmin, DynamicArrayMixin):
    form = CollectionBlockAdminForm
    radio_fields = {'align_type': admin.VERTICAL}
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        fields = fieldsets[0][1]['fields']
        names = ['fixed', 'name1', 'name2', 'name3', 'has_file',
                 'min_items', 'max_items', 'align_type', 'file_optional']
        
        if not obj: add = names[:5]
        elif obj.fixed: add = names[:4] + ['choices']
        elif not obj.has_file: add = names[:8]
        else: add = names[:]
        
        main = ['name', 'page'] + add
        if not obj: return [(None, {'fields': main})]
        
        options = fieldsets[1][1]['fields']
        names += ['name', 'page', 'file_types', 'max_filesize',
                  'autoinit_filename', 'choices', 'wide']
        options += [ f for f in fields if f not in names ]
        if obj.has_file:
            options += ['file_types', 'max_filesize', 'autoinit_filename']
            total, processing = False, {}
            for name in obj.allowed_filetypes() or []:
                filetype = FileType.by_type(name)()
                if filetype.admin_limit_fields(): options.append(name)
                if filetype.admin_processing_fields(): processing[name] = True
                if filetype.admin_total_fields(): total = True
            if total: options.append('total')
            for name in processing: options.append(name + '_proc')
        
        if obj.name1 and obj.name2: options.append('wide')
        
        sets = [(None, {'fields': main}), ('Options', {'fields': options})]
        return sets + fieldsets[2:]
    
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        
        if obj: fields += ('fixed', 'has_file')
        if obj and obj.form.status != Form.Status.DRAFT:
            fields += ('name1', 'name2', 'name3')
        
        return fields


class SuperuserAccessMixin:
    def has_module_permission(self, request): return request.user.is_superuser
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class SiteAccessMixin:
    def has_change_permission(self, request, obj=None):
        slug = self.model._meta.program_slug
        site = get_current_site(request)
        
        programs = user_programs(site.programs, '', request)
        return slug in programs.values_list('db_slug', flat=True)
    
    def has_view_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)
    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)
    def has_add_permission(self, request):
        return self.has_change_permission(request, None)


class SubmittedListFilter(admin.SimpleListFilter):
    title = 'status'
    parameter_name = '_submitted'
    
    def lookups(self, request, model_admin):
        return (('yes', 'submitted'), ('no', 'unsubmitted'))
    
    def queryset(self, request, queryset):
        if self.value() == 'yes': return queryset.exclude(_submitted=None)
        if self.value() == 'no': return queryset.filter(_submitted=None)


class SubmissionRecordFormSet(forms.BaseModelFormSet):
    @classmethod
    def get_default_prefix(cls): return 'formative-submissionrecord'

class SubmissionRecordInline(admin.TabularInline):
    model = SubmissionRecord
    formset = SubmissionRecordFormSet
    exclude = ('program', 'form', 'submission')
    readonly_fields = ('type', 'recorded', 'text', 'number', 'deleted')
    
    def has_add_permission(self, request, obj): return False
    
    def get_formset(self, request, obj=None, **kwargs):
        return forms.modelformset_factory(self.model, **{
            'form': self.form, 'formset': self.formset, 'fields': (),
            'formfield_callback': partial(self.formfield_for_dbfield,
                                          request=request),
            'extra': 0, 'max_num': 0, 'can_delete': False, 'can_order': False
        })


class SubmissionAdmin(SiteAccessMixin, SubmissionActionsMixin,
                      admin.ModelAdmin):
    list_display = ('_email', '_created', '_modified', '_submitted')
    list_filter = ('_email', SubmittedListFilter)
    readonly_fields = ('_submitted', 'items_index',)
    form = SubmissionAdminForm
    inlines = [SubmissionRecordInline]
    actions = ['send_email', 'export_csv', 'download_files']
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        desc = 'Delete selected submissions'
        if 'delete_selected' not in actions: return actions
        actions['delete_selected'][0].short_description = desc
        return actions
    
    def delete_queryset(self, request, queryset):
        # something is up with model registry. manually delete the related items
        related = queryset.model._get_form().item_model.objects
        related.filter(_submission__in=queryset.values_list('pk',
                                                            flat=True)).delete()
        super().delete_queryset(request, queryset)
    
    def get_formsets_with_inlines(self, request, obj=None):
        for inl in self.get_inline_instances(request, obj):
            if not isinstance(inl, SubmissionRecordInline) or obj is not None:
                yield inl.get_formset(request, obj), inl
    
    def get_formset_kwargs(self, request, obj, inline, prefix):
        args = super().get_formset_kwargs(request, obj, inline, prefix)
        for n in ('instance', 'save_as_new'): args.pop(n, None)
        args['queryset'] = SubmissionRecord.objects.filter(submission=obj.pk)
        return args
    
    @admin.display(description='items')
    def items_index(self, obj):
        app, name = self.model._meta.app_label, self.model._meta.model_name
        args = f'?_submission___id__exact={obj._id}'
        try:
            url = reverse('admin:%s_%s_changelist' % (app, name + '_i'),
                          current_app=self.admin_site.name) + args
        except NoReverseMatch: return ''
        
        return mark_safe(f'<a href="{url}">items listing</a>')
    
    def view_on_site(self, obj):
        url = obj._get_absolute_url()
        if obj._submitted: url += 'review'
        return url


class SubmissionItemAdmin(SiteAccessMixin, admin.ModelAdmin):
    list_display = ('_id', '_submission', '_collection', '_rank', '_file')
    list_filter = (
        '_submission', '_collection',
        ('_file', admin.EmptyFieldListFilter)
    )
    readonly_fields = ('_submission', '_block', '_rank')
    ordering = ('_submission', '_collection', '_block', '_rank')
    form = SubmissionItemAdminForm
    
    def has_add_permission(self, request):
        return False


@admin.register(Site, site=site)
class SiteAdmin(SuperuserAccessMixin, admin.ModelAdmin):
    form = SiteAdminForm
    list_display = ('domain', 'name', 'time_zone')
    search_fields = ('domain', 'name')
    
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.site: return queryset.filter(pk=request.user.site.pk)
        return queryset
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Site.objects.clear_cache()
    
    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        Site.objects.clear_cache()
