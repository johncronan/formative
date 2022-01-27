from django.core import validators
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import re

from .utils import get_file_extension, human_readable_filesize


class WordValidator(validators.BaseValidator):
    pattern = re.compile(r'\w+')
    
    def clean(self, x):
        return len(self.pattern.findall(x))


class MinWordsValidator(WordValidator):
    message = _('Ensure this text has at least %(limit_value)d words' +
                ' (it has %(show_value)d).')
    code = 'min_words'

    def compare(self, a, b):
        return a < b


class MaxWordsValidator(WordValidator):
    message = _('Ensure this text has at most %(limit_value)d words' +
                ' (it has %(show_value)d).')
    code = 'max_words'

    def compare(self, a, b):
        return a > b


class FileExtensionValidator(validators.FileExtensionValidator):
    MAX_EXTENSION_LENGTH = 10
    message = 'Allowed file extensions are: %(allowed_extensions)s.'
    
    def __call__(self, value):
        if self.allowed_extensions is None:
            # validate that there is some extension
            extension = get_file_extension(value)
            if not extension or len(extension) > self.MAX_EXTENSION_LENGTH:
                message = _('File name must end with an extension.')
                raise ValidationError(message, code='no_extension',
                                      params={'extension': extension,
                                              'value': value})
            return
        
        class NameAsFile:
            pass
        f = NameAsFile()
        f.name = value
        
        super().__call__(f)


class FileSizeValidator(validators.MaxValueValidator):
    message = _('Maximum file size is %(val_with_unit)s.')
    
    def __call__(self, value):
        params = {'val_with_unit': human_readable_filesize(self.limit_value)}
        if self.compare(value, self.limit_value):
            raise ValidationError(self.message, code=self.code, params=params)
