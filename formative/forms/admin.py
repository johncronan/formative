from django import forms
from django.core.exceptions import ValidationError
from copy import deepcopy
from django_better_admin_arrayfield.forms.fields import DynamicArrayField

from ..stock import StockWidget
from ..models import FormBlock, CustomBlock


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


class AdminJSONFormMetaclass(forms.models.ModelFormMetaclass):
    def __new__(cls, class_name, bases, attrs):
        json_fields, fields, dynamic_fields, static_fields = {}, [], [], []
        if 'Meta' in attrs:
            json_fields = deepcopy(getattr(attrs['Meta'], 'json_fields', {}))
            fields = list(getattr(attrs['Meta'], 'fields', []))
            dynamic_fields = getattr(attrs['Meta'], 'dynamic_fields', False)
            static_fields = list(getattr(attrs['Meta'], 'static_fields', []))
        
        def json_field_callback(field, **kwargs):
            if field.name not in json_fields.keys():
                return field.formfield(**kwargs)
            return JSONPseudoField(required=False)
        
        if json_fields:
            attrs['formfield_callback'] = json_field_callback
            exclude_fields = []
            # Meta.static_fields must be used for dynamic_fields forms
            if dynamic_fields and hasattr(bases[0].Meta, 'static_fields'):
                for f in fields:
                    # requested fields not in parent form class are dynamic ones
                    if f not in bases[0].Meta.static_fields:
                        # non-model fields have to be statically declared
                        exclude_fields.append(f) # remove; added back, in init
            
            fields = [ f for f in fields
                       if f not in json_fields and f not in exclude_fields ]
            if fields: attrs['Meta'].fields = list(json_fields.keys()) + fields
        
        new_class = super().__new__(cls, class_name, bases, attrs)
        
        new_class._meta.json_fields = json_fields
        new_class._meta.static_fields = static_fields
        return new_class


class AdminJSONForm(forms.ModelForm, metaclass=AdminJSONFormMetaclass):
    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs and kwargs['instance']:
            instance, initial = kwargs['instance'], {}
            if 'initial' in kwargs: initial = kwargs['initial']
            
            for name, fields in self._meta.json_fields.items():
                value = getattr(instance, name)
                for field in fields:
                    if field in value: initial[field] = value[field]
            
            kwargs['initial'] = initial
        
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = self.cleaned_data
        for name, fields in self._meta.json_fields.items():
            if not cleaned_data[name]: cleaned_data[name] = {}
            
            for field in fields:
                if field not in cleaned_data: continue
                if isinstance(self.fields[field], forms.BooleanField):
                    if cleaned_data[field]:
                        cleaned_data[name][field] = cleaned_data[field]
                    else: cleaned_data[name].pop(field, None)
                else:
                    if cleaned_data[field] is not None:
                        cleaned_data[name][field] = cleaned_data[field]
                    else: cleaned_data[name].pop(field, None)
        
        return cleaned_data


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
                             widget=forms.RadioSelect)
    no_review = NegatedBooleanField(label='show in review', required=False)
    
    class Meta:
        exclude = ('form',)
        static_fields = ('name', 'page', 'type', 'no_review',
                         'dependence', 'negate_dependencies')
        json_fields = {'options': ['type', 'no_review']}
        dynamic_fields = True
    
    def __init__(self, *args, **kwargs):
        self.admin_fields = None
        if 'instance' in kwargs and kwargs['instance']:
            stock = kwargs['instance'].stock
            admin_fields = stock.admin_fields()
            self.admin_fields = tuple(admin_fields.keys())
            # safe to modify the values of json_fields, just not the keys:
            self._meta.json_fields['options'] += list(admin_fields.keys())
        
        super().__init__(*args, **kwargs)
        
        if self.admin_fields:
            for name, field in admin_fields.items():
                self.fields[name] = field
    
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


class CollectionBlockAdminForm(FormBlockAdminForm, AdminJSONForm):
    no_review = NegatedBooleanField(label='show in review', required=False)
    
    class Meta:
        exclude = ('form', 'align_type')
        json_fields = {'options': ['no_review']}
