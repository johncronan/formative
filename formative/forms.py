from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from .models import CustomBlock, SubmissionItem
from .validators import MinWordsValidator, MaxWordsValidator, \
    FileExtensionValidator


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    def __init__(self, custom_blocks=None, stock_blocks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_blocks = custom_blocks
        self.stock_blocks = stock_blocks
        
        for name, field in self.fields.items():
            if name in stock_blocks:
                stock = stock_blocks[name]

                widget = stock.get_widget(name)
                field.validators += stock.field_validators(widget)

                if stock.field_required(widget): field.required = True
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
        
        stocks = {}
        
        for name, field in self.fields.items():
            if name in self.stock_blocks:
                stock = self.stock_blocks[name]
                if stock.name not in stocks: stocks[stock.name] = [stock, {}]
                
                widget = stock.get_widget(name)
                if widget:
                    stocks[stock.name][1][widget] = self.cleaned_data[name]
                else: stocks[stock.name][1] = self.cleaned_data[name]
                
                if self.has_error(name): stocks[stock.name][0] = False
                
            if name in self.custom_blocks:
                block = self.custom_blocks[name]
                if self.has_error(name): continue

                err = block.clean_field(self.cleaned_data[name], field)
                if err: self.add_error(name, err)
                
                if block.type == CustomBlock.InputType.CHOICE:
                    # NULL for fields that're never seen; '' for no choice made
                    if self.cleaned_data[name] is None:
                        self.cleaned_data[name] = ''
        
        for name, (stock, data) in stocks.items():
            if not stock: continue # show validator errors on form fields first
            
            err = stock.clean(data)
            if not err: continue
            
            if not stock.composite:
                self.add_error(name, err)
                continue
            for widget, err in err.items():
                if widget: self.add_error(stock.field_name(widget), err)
                else: self.add_error(None, err)


class ItemFileForm(forms.Form):
    name = forms.CharField(max_length=SubmissionItem._filename_maxlen(),
                           error_messages={
        'max_length': _('File name cannot exceed %(limit_value)d characters')
    })
    size = forms.IntegerField(error_messages={
        # TODO: human readable
        'max_value': _('Maximum file size is %(limit_value)d bytes.')
    })
    
    def __init__(self, block=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.block = block
        
        if block.file_optional:
            self.fields['name'].required = False
            self.fields['size'].required = False
        
        maxsize = block.file_maxsize()
        if maxsize:
            self.fields['size'].validators.append(MaxValueValidator(maxsize))
        
        extensions = self.block.allowed_extensions()
        validator = FileExtensionValidator(allowed_extensions=extensions)
        self.fields['name'].validators.append(validator)
        
        # TODO: extension claimed by allowed type; maxsize by file type


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
        
        if not self.block.min_items and not self.block.max_items: return
        n = self.instance._items.filter(_block=self.block.pk).count()
        
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
