from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageFile
import os

from ..utils import thumbnail_path
from . import FileType

ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageFile(FileType):
    TYPE = 'image'
    EXTENSIONS = ('jpg', 'jpeg', 'gif')
    
    def meta(self, path):
        ret = super().meta(path)
        
        try:
            with Image.open(path) as img:
                width, height = img.size
            ret.update(width=width, height=height,
                       megapixels=width*height/1000000)
            return ret
        except:
            msg = _('Error occurred processing the image file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
    
    def submitted(self, items):
        for item in items:
            file = item._file
            with Image.open(file.path) as img:
                if img.mode != 'RGB': img = img.convert('RGB')
                img.thumbnail((120, 120), Image.ANTIALIAS)
                # TODO: need an alternative name thing
                outpath = thumbnail_path(file.path)
                if os.path.isfile(outpath): continue
                
                img.save(outpath, img.format)
                        
