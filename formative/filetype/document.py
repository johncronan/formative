from django.utils.translation import gettext_lazy as _
from pikepdf import Pdf

from . import FileType


class DocumentFile(FileType):
    TYPE = 'document'
    EXTENSIONS = ('pdf',)
    
    def meta(self, path):
        try:
            with Pdf.open(path) as pdf:
                pages = len(pdf.pages)
            return {'pages': pages}
        
        except:
            msg = _('Error occurred processing the PDF file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
