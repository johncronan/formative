from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageFile
import logging

from . import FileType

ImageFile.LOAD_TRUNCATED_IMAGES = True
logger = logging.getLogger('django.request')


class ImageFile(FileType):
    TYPE = 'image'
    EXTENSIONS = ('jpg', 'jpeg', 'gif')
    
    def meta(self, path):
        try:
            im = Image.open(path)
            width, height = im.size
            return {'width': width, 'height': height}
        
        except:
            msg = _('Error occurred processing the image file.')
            logger.exception(msg)
            return {'error': msg}
