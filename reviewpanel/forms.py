from django import forms


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    class Meta:
        pass

    def __init__(self, custom_blocks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_blocks = custom_blocks
        
        for name, field in self.fields.items():
            if type(field) == forms.TypedChoiceField:
                # TODO: use formfield_callback instead, to specify empty_label
                self.fields[name].choices = field.choices[1:]

    def clean(self):
        super().clean()
        for name, field in self.fields.items():
            if name in self.custom_blocks:
                block = self.custom_blocks[name]
                
                err = block.clean_field(self.cleaned_data[name], field)
                if err: self.add_error(name, err)
