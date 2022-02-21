from django import forms
from django.core.exceptions import ValidationError
from django.contrib.admin import widgets
from copy import deepcopy
from django_better_admin_arrayfield.forms.fields import DynamicArrayField
from django_better_admin_arrayfield.forms.widgets import DynamicArrayWidget

import datetime

from ..signals import register_program_settings, register_form_settings
from ..filetype import FileType
from ..stock import StockWidget
from ..models import Program, Form, FormBlock, CustomBlock, \
    Submission, SubmissionItem


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
    
    def has_changed(self, initial, data):
        return (not self.to_python(initial)) != self.to_python(data)


DISPLAY_MAX = 9999999999

class SplitDictWidget(forms.MultiWidget):
    template_name = 'admin/formative/widgets/split_dict.html'
    
    def __init__(self, fields, two_column=False, attrs=None):
        self.fields, self.two_column = fields, two_column
        
        subwidgets = {}
        for name, field in fields.items():
            widget = forms.TextInput(attrs=attrs)
            if isinstance(field, forms.IntegerField):
                if not attrs: int_attrs = {}
                else: int_attrs = attrs.copy()
                
                int_attrs['min'], int_attrs['max'] = 0, DISPLAY_MAX
                if name.startswith('min_'):
                    int_attrs['placeholder'] = 'minimum'
                elif name.startswith('max_'):
                    int_attrs['placeholder'] = 'maximum'
                
                widget = widgets.AdminIntegerFieldWidget(attrs=int_attrs)
            subwidgets[name] = widget
        
        super().__init__(subwidgets)
    
    def decompress(self, val):
        if val:
            ret = []
            for name, field in self.fields.items():
                if name in val: ret.append(val[name])
                else: ret.append(None)
            return ret
        return [None] * len(self.fields)
    
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['two_column'] = self.two_column
        for widget in context['widget']['subwidgets']:
            name = widget['name'][widget['name'].index('_')+1:]
            if name.startswith('min_') or name.startswith('max_'):
                name = name[4:]
            widget['short_name'] = name
        
        return context


class SplitDictField(forms.MultiValueField):
    widget = SplitDictWidget
    
    def __init__(self, fields, **kwargs):
        self.fields_dict = fields
        super().__init__(fields.values(), **kwargs)
    
    def compress(self, data):
        if not data: return None
        ret = {}
        for i, (name, field) in enumerate(self.fields_dict.items()):
            if data[i] is not None: ret[name] = data[i]
        if ret: return ret
        return None


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
            
            if fields and fields != forms.ALL_FIELDS:
                fields = [ f for f in fields
                           if f not in json_fields and f not in exclude_fields ]
                json_keys = {}
                for field in json_fields:
                    if '.' in field: val = field[:field.index('.')]
                    else: val = field
                    json_keys[val] = True
                attrs['Meta'].fields = list(json_keys) + fields
        
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
                if '.' in name:
                    p1, p2 = name[:name.index('.')], name[name.index('.')+1:]
                    json = getattr(instance, p1)
                    if p2 not in json: value = {}
                    else: value = json[p2]
                else: value = getattr(instance, name)
                
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
            base, part = name, None
            if '.' in name: base = name[:name.index('.')]
            
            if not cleaned_data[base]: cleaned_data[base] = {}
            dest = cleaned_data[base]
            if '.' in name:
                part = name[name.index('.')+1:]
                if part not in dest: dest[part] = {}
                dest = dest[part]
            
            for field in fields:
                if field not in cleaned_data: continue
                
                test = bool
                if isinstance(self.fields[field], forms.BooleanField): pass
                elif isinstance(self.fields[field], forms.CharField): pass
                elif isinstance(self.fields[field], forms.ChoiceField): pass
                elif isinstance(self.fields[field], SplitDictField): pass
                else: test = lambda x: x is not None
                
                if test(cleaned_data[field]): dest[field] = cleaned_data[field]
                else: dest.pop(field, None)
            
            if '.' in name and not dest: cleaned_data[base].pop(part, None)
        
        return cleaned_data


class ProgramAdminForm(AdminJSONForm):
    name = forms.CharField(
        max_length=Program._meta.get_field('name').max_length,
        widget=widgets.AdminTextInputWidget,
        help_text='Full name, displayed on the listing of forms.'
    )
    slug = forms.SlugField(
        label='identifier', allow_unicode=True, max_length=30,
        widget=forms.TextInput(attrs={'size': 32}),
        help_text='A short name to uniquely identify the program. '
                  'Cannot be changed.'
    )
    home_url = forms.URLField(
        required=False,
        help_text='URL for the home icon link, when viewing this program.'
    )
    
    class Meta:
        static_fields = ('name', 'slug', 'description', 'hidden', 'home_url')
        json_fields = {'options': ['home_url']}
        dynamic_fields = True
        widgets = {
            'description': widgets.AdminTextareaWidget(attrs={'rows': 3})
        }
    
    def __init__(self, *args, **kwargs):
        if 'instance' in kwargs and kwargs['instance']:
            responses = register_program_settings.send(self)
            admin_fields = { k: v for _, r in responses for k, v in r.items() }
            self._meta.json_fields['options'] += list(admin_fields.keys())
            kwargs['admin_fields'] = admin_fields
        
        super().__init__(*args, **kwargs)


class FormAdminForm(AdminJSONForm):
    name = forms.CharField(
        max_length=Form._meta.get_field('name').max_length,
        widget=widgets.AdminTextInputWidget,
        help_text='Full name, displayed on the form.'
    )
    slug = forms.SlugField(
        label='identifier', allow_unicode=True, max_length=30,
        widget=forms.TextInput(attrs={'size': 32}),
        help_text='A short name to uniquely identify the form. '
                  'Cannot be changed after publishing.'
    )
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
        static_fields = ('program', 'name', 'slug', 'status', 'hidden')
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
    numeric_min = forms.IntegerField(required=False)
    numeric_max = forms.IntegerField(required=False)
    
    class Meta:
        exclude = ('form',)
        json_fields = {'options': ['no_review', 'choices',
                                   'numeric_min', 'numeric_max']}
    
    def __init__(self, *args, **kwargs):
        block = None
        if 'instance' in kwargs and kwargs['instance']:
            block = kwargs['instance']
        
        super().__init__(*args, **kwargs)
        
        if not block: del self.fields['choices'], self.fields['no_review']
        if block:
            if block.type != CustomBlock.InputType.CHOICE:
                del self.fields['choices']
            if block.type != CustomBlock.InputType.NUMERIC:
                del self.fields['numeric_min'], self.fields['numeric_max']


class CollectionBlockAdminForm(FormBlockAdminForm, AdminJSONForm):
    no_review = NegatedBooleanField(label='show in review', required=False)
    button_text = forms.CharField(
        required=False,
        help_text="Label for the collection's 'add' button. "
                  "Defaults to 'add item' or 'add file' or 'add files.'"
    )
    file_types = DynamicArrayField(
        forms.ChoiceField(choices=[ (n, n) for n in FileType.types.keys() ]),
        required=False,
        help_text='Available types are: '+', '.join(FileType.types.keys())+'. '
                  'Leave empty to allow any file type.'
    ) # TODO what if the set of available file types (or stocks) changes?
    max_filesize = forms.IntegerField(
        required=False, help_text='bytes. Applies to any type of file.',
        widget=widgets.AdminIntegerFieldWidget
    )
    autoinit_filename = forms.ChoiceField(
        required=False,
        help_text="If selected, the text field's default will be the file name."
    )
    
    class Meta:
        exclude = ('form', 'align_type')
        static_fields = ('name', 'page', 'fixed', 'name1', 'name2', 'name3',
                         'has_file', 'min_items', 'max_items', 'file_optional',
                         'dependence', 'negate_dependencies')
        json_fields = {'options': ['no_review', 'fieldtest']}
        dynamic_fields = True
    
    def __init__(self, *args, **kwargs):
        block, file_limits = None, {}
        if 'instance' in kwargs and kwargs['instance']:
            block = kwargs['instance']
            fields = ['button_text']
            if block.has_file:
                fields += ['file_types', 'max_filesize', 'autoinit_filename']
                self._meta.json_fields['options'] += fields
                
                admin_fields, total_fields = {}, {}
                self._meta.json_fields['options.file_limits'] = []
                for name in block.allowed_filetypes() or []:
                    filetype = FileType.by_type(name)()
                    fields = {}
                    for n in filetype.admin_limit_fields():
                        fields['min_' + n] = forms.IntegerField()
                        fields['max_' + n] = forms.IntegerField()
                    for n in filetype.admin_total_fields():
                        total_fields['min_' + n] = forms.IntegerField()
                        total_fields['max_' + n] = forms.IntegerField()
                    
                    admin_fields[name] = SplitDictField(
                        fields, required=False,
                        widget=SplitDictWidget(fields, two_column=True),
                        label=name+' limits'
                    )
                    self._meta.json_fields['options.file_limits'].append(name)
                
                admin_fields['total'] = SplitDictField(
                    total_fields, required=False,
                    widget=SplitDictWidget(total_fields, two_column=True),
                    label='total limits',
                    help_text='Limits that apply to the total value, '
                              'for all files (when field is applicable).'
                )
                self._meta.json_fields['options.file_limits'].append('total')
                
                kwargs['admin_fields'] = admin_fields
        
        super().__init__(*args, **kwargs)
        
        if not block: del self.fields['no_review'], self.fields['button_text']
        if not block or not block.has_file:
             for n in ('file_types', 'max_filesize', 'autoinit_filename'):
                del self.fields[n]
        else:
            choices = [ (n, n) for n in block.collection_fields() ]
            self.fields['autoinit_filename'].choices = [(None, '-')] + choices
    
    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        
        if not self.instance: return cleaned_data
        if 'autoinit_filename' in cleaned_data:
            field = cleaned_data['autoinit_filename']
            if field not in self.instance.collection_fields():
                del cleaned_data['options']['autoinit_filename']
        return cleaned_data


class SubmissionAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        for name, field in self.fields.items():
            if name == '_email': field.required = True
            elif field.required: field.required = False


class SubmissionItemAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        for n, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField): continue
            if n in [ f.name for f in  SubmissionItem._meta.fields ]: continue
            if field.required: field.required = False
