from django import forms
from copy import deepcopy
from django_better_admin_arrayfield.forms.fields import DynamicArrayField
from django_better_admin_arrayfield.forms.widgets import DynamicArrayWidget

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
        json_fields, fields = {}, []
        if 'Meta' in attrs:
            json_fields = deepcopy(getattr(attrs['Meta'], 'json_fields', {}))
            fields = list(getattr(attrs['Meta'], 'fields', []))
        
        def json_field_callback(field, **kwargs):
            if field.name not in json_fields.keys():
                return field.formfield(**kwargs)
            return JSONPseudoField()
        
        if json_fields:
            attrs['formfield_callback'] = json_field_callback
            attrs['fields'] = list(json_fields.keys()) + fields
        new_class = super().__new__(cls, class_name, bases, attrs)
        
        new_class._meta.json_fields = json_fields
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
                if isinstance(self.base_fields[field], forms.BooleanField):
                    if cleaned_data[field]:
                        cleaned_data[name][field] = cleaned_data[field]
                    else: cleaned_data[name].pop(field, None)
                else:
                    cleaned_data[name][field] = cleaned_data[field]
        
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
        json_fields = {'options': ['type', 'no_review']}


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
