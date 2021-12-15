from django import forms


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')


class SubmissionForm(forms.ModelForm):
    class Meta:
        pass
