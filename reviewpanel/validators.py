from django.core.validators import BaseValidator
from django.utils.translation import gettext_lazy as _
import re


class WordValidator(BaseValidator):
    pattern = re.compile(r'\w+')
    
    def clean(self, x):
        return len(self.pattern.findall(x))


class MinWordsValidator(WordValidator):
    message = _('Ensure this value has at least %(limit_value)d words' +
                ' (it has %(show_value)d).')
    code = 'min_words'

    def compare(self, a, b):
        return a < b


class MaxWordsValidator(WordValidator):
    message = _('Ensure this value has at most %(limit_value)d words' +
                ' (it has %(show_value)d).')
    code = 'max_words'

    def compare(self, a, b):
        return a > b
