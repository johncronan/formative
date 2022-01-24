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
            msg = _('Error occurred reading the image file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
    
    def process(self, path, meta, max_width=None, max_height=None, **kwargs):
        if not max_width and not max_height: return meta
        if meta['width'] <= max_width and meta['height'] <= max_height:
            return meta
        
        try:
            with Image.open(path) as img:
                img.load()
                img.thumbnail((max_width, max_height), Image.ANTIALIAS)
                new_width, new_height = img.size
                img.save(path, img.format)
            meta['width'], meta['height'] = new_width, new_height
            meta['megapixels'] = new_width * new_height / 1000000
            msg = _('Image was resized to %(width)sx%(height)s.')
            meta['message'] = msg % {'width': new_width, 'height': new_height}
            return meta
        except:
            msg = _('Error occurred processing the image file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
    
    def submitted(self, items):
        for item in items:
            file = item._file
            try:
                with Image.open(file.path) as img:
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.thumbnail((120, 120), Image.ANTIALIAS)
                    # TODO: need an alternative name thing
                    outpath = thumbnail_path(file.path)
                    if not os.path.isfile(outpath):
                        img.save(outpath, img.format)
            except:
                self.logger.critical('Error generating thumbnail.',
                                     exc_info=True)
