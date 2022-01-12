from django import forms
from django.core.validators import MaxValueValidator
from django.utils.translation import gettext_lazy as _

from .models import CustomBlock, SubmissionItem
from .validators import MinWordsValidator, MaxWordsValidator


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    class Meta:
        pass

    def __init__(self, custom_blocks=None, stock_blocks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_blocks = custom_blocks
        self.stock_blocks = stock_blocks
        
        for name, field in self.fields.items():
            if name in stock_blocks:
                stock = stock_blocks[name]

                widget = None
                if len(stock.widget_names()) > 1:
                    widget = name[1:][len(stock.name)+1:]
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
        
        for name, field in self.fields.items():
            if name in self.custom_blocks:
                block = self.custom_blocks[name]
                if self.has_error(name): continue

                err = block.clean_field(self.cleaned_data[name], field)
                if err: self.add_error(name, err)
                
                if block.type == CustomBlock.InputType.CHOICE:
                    # NULL for fields that're never seen; '' for no choice made
                    if self.cleaned_data[name] is None:
                        self.cleaned_data[name] = ''


class ItemFileForm(forms.Form):
    # TODO: validate that there's an extension
    name = forms.CharField(max_length=SubmissionItem.filename_maxlen(),
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
        
        # TODO: maxsize by file type


class ItemsFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    # we can have sparse form indices in the request kwarg data (due to deletes)
    # so the total form count that we get is actually a max possible index.
    # this is where we filter out invalid forms in the formset that result
    def is_valid(self):
        if not self.is_bound: return False
        
        self.errors # triggers a full clean the first time only
        
        forms_valid = all([ form.is_valid() for i, form in enumerate(self.forms)
                            if self.prefix + f'-{i}-_id' in form.data])
        
        return forms_valid and not self.non_form_errors()
