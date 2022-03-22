from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.formats import date_format, time_format
from django.utils.translation import gettext_lazy as _
from datetime import timedelta

from ..models import Form, CustomBlock, SubmissionItem
from ..filetype import FileType
from ..validators import MinWordsValidator, MaxWordsValidator, \
    FileExtensionValidator, FileSizeValidator
from ..utils import get_file_extension, human_readable_filesize


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    def __init__(self, program_form=None, custom_blocks=None, stock_blocks=None,
                 page=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.program_form = program_form
        self.custom_blocks = custom_blocks
        self.stock_blocks = stock_blocks
        self.page = page
        
        for name, field in self.fields.items():
            if name in stock_blocks:
                stock = stock_blocks[name]
                
                widget = stock.get_widget(name)
                field.validators += stock.field_validators(widget)
                
                if stock.field_required(widget): field.required = True
                
                if type(field) == forms.TypedChoiceField:
                    if not field.initial: field.choices = field.choices[1:]
                continue
            
            block = custom_blocks[name]
            if type(field) == forms.TypedChoiceField:
                # TODO: report bug with passing empty_label to .formfield()
                field.choices = field.choices[1:]
            elif type(field) == forms.CharField:
                if block.min_words:
                    field.validators.append(MinWordsValidator(block.min_words))
                if block.max_words:
                    field.validators.append(MaxWordsValidator(block.max_words))

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        
        if not self.page and self.program_form.status != Form.Status.ENABLED:
            msg, params = _('Application cannot be submitted. '), {}
            if self.program_form.status == Form.Status.COMPLETED:
                if self.program_form.extra_time(): msg = None
                else: msg += _('This form closed on %(date)s at %(time)s.')
                
                comp = self.program_form.completed
                params = {
                    'time': time_format(comp.time(), format='TIME_FORMAT'),
                    'date': date_format(comp.date(), format='SHORT_DATE_FORMAT')
                }
            else: msg += _('Submissions are temporarily disabled.')
            
            if msg:
                self.add_error(None, ValidationError(msg, params=params))
                return
        
        stocks = {}
        for name, field in self.fields.items():
            if name in self.custom_blocks:
                block = self.custom_blocks[name]
                if self.has_error(name): continue
                
                try: data = block.clean_field(cleaned_data[name], field)
                except ValidationError as e: self.add_error(name, e.message)
                else: self.cleaned_data[name] = data
                
                if block.type in (CustomBlock.InputType.TEXT,
                                  CustomBlock.InputType.CHOICE):
                    # NULL for fields that're never seen; '' for no choice made
                    if cleaned_data[name] is None: self.cleaned_data[name] = ''
        
            elif name in self.stock_blocks:
                stock = self.stock_blocks[name]
                if stock.name not in stocks: stocks[stock.name] = [stock, {}]
                
                if self.has_error(name):
                    stocks[stock.name][0] = False
                    continue
                widget = stock.get_widget(name)
                if widget: stocks[stock.name][1][widget] = cleaned_data[name]
                else: stocks[stock.name][1] = cleaned_data[name]
            
        for name, (stock, data) in stocks.items():
            if not stock: continue # show validator errors on form fields first
            
            fields = stock.clean(data)
            
            if not stock.composite:
                if type(fields) == ValidationError:
                    self.add_error(name, err)
                else: self.cleaned_data[name] = fields
                continue
            err = False
            for widget, val in fields.items():
                if type(val) == ValidationError:
                    if widget: self.add_error(stock.field_name(widget), val)
                    else: self.add_error(None, val)
                    err = True
            if not err:
                for widget, val in fields.items():
                    self.cleaned_data[stock.field_name(widget)] = val


class ItemFileForm(forms.Form):
    name = forms.CharField(max_length=SubmissionItem._filename_maxlen(),
                           error_messages={
        'max_length': _('File name cannot exceed %(limit_value)d characters.')
    })
    size = forms.IntegerField()
    
    def __init__(self, block=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.block = block
        
        if block.file_optional:
            self.fields['name'].required = False
            self.fields['size'].required = False
        
        maxsize = block.max_filesize()
        if maxsize:
            self.fields['size'].validators.append(FileSizeValidator(maxsize))
        
        extensions = self.block.allowed_extensions()
        validator = FileExtensionValidator(allowed_extensions=extensions)
        self.fields['name'].validators.append(validator)
        
    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data
        if 'name' not in cleaned_data: return
        
        extension = get_file_extension(self.cleaned_data['name'])
        filetype = FileType.by_extension(extension)
        limits = self.block.file_limits()
        
        if filetype and filetype.TYPE in limits:
            if 'max_filesize' in limits[filetype.TYPE]:
                maxval = limits[filetype.TYPE]['max_filesize']
                if cleaned_data['size'] > maxval:
                    msg = _('Maximum file size for this type of file is '
                            '%(limit_value)s.')
                    params = {'limit_value': human_readable_filesize(maxval)}
                    raise ValidationError(msg, code='max_value', params=params)
            
            if 'min_filesize' in limits[filetype.TYPE]:
                maxval = limits[filetype.TYPE]['min_filesize']
                if cleaned_data['size'] < maxval:
                    msg = _('Minimum file size for this type of file is '
                            '%(limit_value)s.')
                    params = {'limit_value': human_readable_filesize(minval)}
                    raise ValidationError(msg, code='min_value', params=params)


class ItemsForm(forms.ModelForm):
    def __init__(self, block=None, field_blocks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.block = block
        self.field_blocks = field_blocks
        
        for name, f in self.fields.items():
            if name in self.field_blocks: field_block = self.field_blocks[name]
            else: field_block = CustomBlock.text_create()
            
            if field_block.min_words:
                f.validators.append(MinWordsValidator(field_block.min_words))
            if field_block.max_words:
                f.validators.append(MaxWordsValidator(field_block.max_words))
    
    def clean(self):
        super().clean()
        
        if self.instance and self.instance._error:
            for name in self.fields.keys():
                if name in self.errors: self.errors.pop(name)
                self.fields[name].required = False # TODO move


class ItemsFormSet(forms.BaseModelFormSet):
    def __init__(self, block=None, instance=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.block, self.instance = block, instance
        
        cfields = block.collection_fields()
        blocks = block.form.custom_blocks().filter(page=0, name__in=cfields)
        self.field_blocks = { b.name: b for b in blocks }
    
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(None) # it just makes a copy
        
        kwargs['block'] = self.block
        kwargs['field_blocks'] = self.field_blocks
        return kwargs
    
    # the way Django formsets index forms in POST data doesn't work well when
    # there's AJAX on the page that can do insertions and deletions.
    # we assume here that the forms in the formset always have a pk'd instance,
    # except for unbound formsets, which can have extra (for fixed collections)
    @cached_property
    def forms(self):
        args_list, objects = [], { str(o.pk): o for o in self.get_queryset() }
        creating = False
        if self.block.fixed and not objects:
            creating = True
            objects = [ str(i) for i in range(self.block.num_choices()) ]
        
        defaults = {
            'auto_id': self.auto_id,
            'error_class': self.error_class,
            'renderer': self.renderer
        }
        def new_kwargs():
            kwargs = self.get_form_kwargs(None)
            kwargs.update(defaults)
            return kwargs
        
        if self.is_bound:
            for key, val in self.data.items():
                if not key.startswith(self.prefix + '-'): continue
                
                if creating: pk_name = '_rank'
                else: pk_name = '_id'
                
                rest = key[len(self.prefix)+1:]
                if not rest.endswith('-' + pk_name): continue
                
                pk_str = rest[:-len(pk_name)-1]
                
                if pk_str in objects:
                    kwargs = new_kwargs()
                    
                    kwargs['prefix'] = self.prefix + '-' + pk_str
                    kwargs['data'], kwargs['files'] = self.data, self.files
                    
                    if not creating:
                        kwargs['instance'] = objects[pk_str]
                    args_list.append(kwargs)
        elif not creating:
            for instance in self.get_queryset():
                kwargs = new_kwargs()
                
                kwargs['instance'] = instance
                kwargs['prefix'] = self.prefix + '-%s' % (instance.pk,)
                args_list.append(kwargs)
        else:
            for i in range(self.extra):
                kwargs = new_kwargs()
                
                kwargs['prefix'] = self.prefix + '-%s' % (i,)
                if self.initial_extra: kwargs['initial'] = self.initial_extra[i]
                args_list.append(kwargs)
        
        forms = []
        for i, kwargs in enumerate(args_list):
                form = self.form(**kwargs)
                self.add_fields(form, i)
                
                if not creating:
                    form.fields[self.model._meta.pk.name].required = True
                forms.append(form)
        
        return forms
    
# still need that management form, for now
#    def initial_form_count(self):
#        if not self.is_bound: return len(self.get_queryset())
#        return len(self.forms)
#    
#    def total_form_count(self):
#        if not self.is_bound: return 0
#        else: return self.initial_form_count()
    
    def clean(self):
        super().clean()
        
        files = self.instance._items.filter(_block=self.block.pk)
        files = files.exclude(_file='', _filesize__gt=0)
        file_errors = files.values_list('_error', flat=True)
        n = len(file_errors)
        if True in file_errors:
            msg = _('Some files have errors.')
            raise ValidationError(msg, code='file_error')
        
        self.valid_num(n)
        
        file_limits = self.block.file_limits()
        if 'total' not in file_limits: return
        
        for key, limit_val in file_limits['total'].items():
            if not (key.startswith('max_') or key.startswith('min_')): continue
            name = key[4:]
            
            if name == 'filesize': name = 'size'
            generic = FileType()
            if name == 'size':
                total = sum(files.values_list('_filesize', flat=True))
            else:
                total = sum(f._filemeta[name] for f in files
                            if name in f._filemeta)
            
            meta = { name: total }
            err = generic.limit_error(meta, {key: limit_val})
            if err: raise ValidationError(err)
    
    def valid_num(self, n):
        if not self.block.min_items and not self.block.max_items: return
        
        params, msg = {}, ''
        if self.block.min_items and self.block.max_items is None:
            if n >= self.block.min_items: return
            
            if self.block.has_file and not self.block.file_optional:
                msg = _('Number of files must be at least %(min_val)d.')
            else: msg = _('Number of items must be at least %(min_val)d.')
            params['min_val'] = self.block.min_items
        elif self.block.max_items is not None and not self.block.min_items:
            if n <= self.block.max_items: return
            
            if self.block.has_file and not self.block.file_optional:
                msg = _('Number of files must be at most %(max_val)d.')
            else: msg = _('Number of items must be at most %(max_val)d.')
            params['max_val'] = self.block.max_items
        else:
            if n >= self.block.min_items and n <= self.block.max_items: return
            
            if self.block.has_file and not self.block.file_optional:
                msg = _('Number of files must be between '
                        '%(min_val)d and %(max_val)d.')
            else: msg = _('Number of items must be between '
                          '%(min_val)d and %(max_val)d.')
            params['min_val'] = self.block.min_items
            params['max_val'] = self.block.max_items
        
        raise ValidationError(msg, code='invalid_num_items', params=params)
