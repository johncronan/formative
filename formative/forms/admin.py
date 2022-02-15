from django import forms
from django.core.exceptions import ValidationError
from django.contrib.admin import widgets
from copy import deepcopy
from django_better_admin_arrayfield.forms.fields import DynamicArrayField

import datetime

from ..signals import register_program_settings, register_form_settings
from ..stock import StockWidget
from ..models import Form, FormBlock, CustomBlock


class NullWidget(forms.Widget):
    @property
    def is_hidden(self): return True
    
    def value_omitted_from_data(self, data, files, name): return False
    
    def render(self, name, value, **kwargs): return ''


class JSONPseudoBoundField(forms.BoundField):
    @property
    def data(self):
        # always start with initial value; other form fields will modify
        return self.initial


class JSONPseudoField(forms.Field):
    widget = NullWidget
    
    def get_bound_field(self, form, field_name):
        return JSONPseudoBoundField(form, self, field_name)


class NegatedBooleanField(forms.BooleanField):
    def prepare_value(self, value): return not value
    
    def to_python(self, value): return not super().to_python(value)


class JSONDateTimeWidget(widgets.AdminSplitDateTime):
    def decompress(self, val):
        if not val: return super().decompress(val)
        
        return super().decompress(datetime.datetime.fromisoformat(val))


class JSONDateTimeField(forms.SplitDateTimeField):
    widget = JSONDateTimeWidget
    
    def compress(self, data):
        val = super().compress(data)
        if not val: return val
        
        return val.isoformat()


class AdminJSONFormMetaclass(forms.models.ModelFormMetaclass):
    def __new__(cls, class_name, bases, attrs):
        json_fields, fields, dynamic_fields, static_fields = {}, [], [], []
        if 'Meta' in attrs:
            json_fields = deepcopy(getattr(attrs['Meta'], 'json_fields', {}))
            fields = getattr(attrs['Meta'], 'fields', [])
            if fields != forms.ALL_FIELDS: fields = list(fields)
            dynamic_fields = getattr(attrs['Meta'], 'dynamic_fields', False)
            static_fields = list(getattr(attrs['Meta'], 'static_fields', []))
        
        def json_field_callback(field, **kwargs):
            if field.name not in json_fields.keys():
                return field.formfield(**kwargs)
            return JSONPseudoField(required=False)
        
        if json_fields:
            attrs['formfield_callback'] = json_field_callback
            exclude_fields = []
            if dynamic_fields:
                # Meta.static_fields must be used for dynamic_fields forms
                init_fields = static_fields
                if not init_fields:
                    if hasattr(bases[0].Meta, 'static_fields'):
                        init_fields = bases[0].Meta.static_fields
                for f in init_fields and fields or []:
                    # requested fields not in base's list are dynamic ones
                    if f not in init_fields:
                        # non-model fields have to be statically declared
                        exclude_fields.append(f) # remove; added back, in init
            
            if fields != forms.ALL_FIELDS:
                fields = [ f for f in fields
                           if f not in json_fields and f not in exclude_fields ]
                if fields:
                    attrs['Meta'].fields = list(json_fields.keys()) + fields
        
        new_class = super().__new__(cls, class_name, bases, attrs)
        
        new_class._meta.json_fields = json_fields
        new_class._meta.static_fields = static_fields
        return new_class


class AdminJSONForm(forms.ModelForm, metaclass=AdminJSONFormMetaclass):
    def __init__(self, *args, admin_fields=None, **kwargs):
        self.admin_fields = admin_fields
        
        if 'instance' in kwargs and kwargs['instance']:
            instance, initial = kwargs['instance'], {}
            if 'initial' in kwargs: initial = kwargs['initial']
            
            for name, fields in self._meta.json_fields.items():
                value = getattr(instance, name)
                for field in fields:
                    if field in value: initial[field] = value[field]
            
            kwargs['initial'] = initial
        
        super().__init__(*args, **kwargs)
        
        if self.admin_fields:
            for name, field in self.admin_fields.items():
                self.fields[name] = field
    
    def clean(self):
        cleaned_data = self.cleaned_data
        for name, fields in self._meta.json_fields.items():
            if not cleaned_data[name]: cleaned_data[name] = {}
            
            for field in fields:
                if field not in cleaned_data: continue
                
                test = bool
                if isinstance(self.fields[field], forms.BooleanField): pass
                elif isinstance(self.fields[field], forms.CharField): pass
                else: test = lambda x: x is not None
                
                if test(cleaned_data[field]):
                    cleaned_data[name][field] = cleaned_data[field]
                else: cleaned_data[name].pop(field, None)
        
        return cleaned_data


class ProgramAdminForm(AdminJSONForm):
    home_url = forms.URLField(required=False)
    
    class Meta:
        static_fields = ('name', 'description', 'hidden', 'home_url')
        json_fields = {'options': ['home_url']}
        dynamic_fields = True
        widgets = {
            'name': widgets.AdminTextInputWidget(),
            'description': widgets.AdminTextInputWidget()
        }
    
    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs and kwargs['instance']:
            responses = register_program_settings.send(self)
            admin_fields = { k: v for _, r in responses for k, v in r.items() }
            self._meta.json_fields['options'] += list(admin_fields.keys())
            kwargs['admin_fields'] = admin_fields
        
        super().__init__(*args, **kwargs)


class FormAdminForm(AdminJSONForm):
    status = forms.ChoiceField(
        choices=Form.Status.choices,
        widget=widgets.AdminRadioSelect(attrs={'class': 'radiolist'})
    )
    hidden = forms.BooleanField(required=False)
    access_enable = forms.CharField(required=False, label='?access= password')
    review_pre = forms.CharField(
        required=False, widget=widgets.AdminTextareaWidget(attrs={'rows': 5}),
        label='pre review text'
    )
    review_post = forms.CharField(
        required=False, widget=widgets.AdminTextareaWidget(attrs={'rows': 5}),
        label='post review text'
    )
    submitted_review_pre = forms.CharField(
        required=False, widget=widgets.AdminTextareaWidget(attrs={'rows': 5}),
        label='submitted pre review text'
    )
    no_review_after_submit = forms.BooleanField(required=False)
    thanks = forms.CharField(
        required=False, widget=widgets.AdminTextareaWidget(attrs={'rows': 5}),
        label='thanks page text'
    )
    
    class Meta:
        static_fields = ('program', 'name', 'status', 'hidden')
        json_fields = {'options': [
            'hidden', 'access_enable', 'review_pre', 'review_post',
            'submitted_review_pre', 'no_review_after_submit', 'thanks'
        ]}
        dynamic_fields = True
        widgets = {
            'name': widgets.AdminTextInputWidget(),
        }
    
    def __init__(self, *args, **kwargs):
        program_form = None
        if 'instance' in kwargs and kwargs['instance']:
            program_form = kwargs['instance']
            
            responses = register_form_settings.send(program_form)
            admin_fields = { k: v for _, r in responses for k, v in r.items() }
            self._meta.json_fields['options'] += list(admin_fields.keys())
            kwargs['admin_fields'] = admin_fields
            
        super().__init__(*args, **kwargs)
        
        if program_form and program_form.status != Form.Status.DRAFT:
            self.fields['status'].choices = self.fields['status'].choices[1:]
        
        if not program_form:
            del self.fields['status']
            for n in ('access_enable', 'review_pre', 'review_post', 'thanks',
                      'submitted_review_pre', 'no_review_after_submit'):
                del self.fields[n]


class FormBlockAdminForm(forms.ModelForm):
    class Meta:
        model = FormBlock
        fields = ('name', 'page', 'dependence', 'negate_dependencies')


def stock_type_display_name(name): # we need a default display name
    # plugins can prefix a type name with "pluginname." to avoid collisions
    return name[name.rfind('.')+1:]


class StockBlockAdminForm(FormBlockAdminForm, AdminJSONForm):
    type = forms.ChoiceField(choices=[ (n, stock_type_display_name(n))
                                       for n in StockWidget.types.keys() ],
                             widget=widgets.AdminRadioSelect)
    no_review = NegatedBooleanField(label='show in review', required=False)
    
    class Meta:
        exclude = ('form',)
        static_fields = ('name', 'page', 'type', 'no_review',
                         'dependence', 'negate_dependencies')
        json_fields = {'options': ['type', 'no_review']}
        dynamic_fields = True
    
    def __init__(self, *args, **kwargs):
        stock = None
        if 'instance' in kwargs and kwargs['instance']:
            stock = kwargs['instance'].stock
            admin_fields = stock.admin_fields()
            # safe to modify the values of json_fields, just not the keys:
            self._meta.json_fields['options'] += list(admin_fields.keys())
            kwargs['admin_fields'] = admin_fields
        
        super().__init__(*args, **kwargs)
        
        if not stock: del self.fields['no_review']
    
    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        if not self.admin_fields: return
        
        data = {}
        for field in self.admin_fields:
            data[field] = cleaned_data[field]
        fields = self.instance.stock.admin_clean(data)
        
        err = False
        for field, val in fields.items():
            if isinstance(val, ValidationError):
                self.add_error(field, val)
                err = True
        if not err:
            for field, val in fields.items():
                self.cleaned_data[field] = val


class CustomBlockAdminForm(FormBlockAdminForm, AdminJSONForm):
    no_review = NegatedBooleanField(label='show in review', required=False)
    choices = DynamicArrayField(
        forms.CharField(max_length=CustomBlock.CHOICE_VAL_MAXLEN),
    )
    
    class Meta:
        exclude = ('form',)
        json_fields = {'options': ['no_review', 'choices']}
    
    def __init__(self, *args, **kwargs):
        block = None
        if 'instance' in kwargs and kwargs['instance']:
            block = kwargs['instance']
        
        super().__init__(*args, **kwargs)
        
        if not block: del self.fields['choices'], self.fields['no_review']
        if block and block.type != CustomBlock.InputType.CHOICE:
            del self.fields['choices']


class CollectionBlockAdminForm(FormBlockAdminForm, AdminJSONForm):
    no_review = NegatedBooleanField(label='show in review', required=False)
    
    class Meta:
        exclude = ('form', 'align_type')
        json_fields = {'options': ['no_review']}
    
    def __init__(self, *args, **kwargs):
        block = None
        if 'instance' in kwargs and kwargs['instance']:
            block = kwargs['instance']
        
        super().__init__(*args, **kwargs)
        
        if not block: del self.fields['no_review']
