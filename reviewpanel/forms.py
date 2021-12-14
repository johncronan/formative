from django import forms


class OpenForm(forms.Form):
    email = forms.EmailField(label='email address')
