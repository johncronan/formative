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
            with Image.open(path) as img:
                width, height = img.size
            return {'width': width, 'height': height,
                    'megapixels': width * height / 1000000}
        
        except:
            msg = _('Error occurred processing the image file.')
            logger.critical(msg, exc_info=True)
            return {'error': msg}
