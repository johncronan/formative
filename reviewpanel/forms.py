from django import forms

from .validators import MinWordsValidator, MaxWordsValidator


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    class Meta:
        pass

    def __init__(self, custom_blocks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_blocks = custom_blocks
        
        for name, field in self.fields.items():
            if name not in custom_blocks: continue

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
