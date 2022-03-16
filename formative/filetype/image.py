from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageFile, ImageOps
import os

from ..utils import thumbnail_path
from . import FileType

ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageFile(FileType):
    TYPE = 'image'
    EXTENSIONS = ('jpg', 'jpeg', 'gif', 'png')
    
    def meta(self, path):
        ret = super().meta(path)
        
        try:
            with Image.open(path) as img:
                width, height = img.size
                icc = img.info.get('icc_profile', '')
                profile = ''
                if icc:
                    profile = ''.join(chr(x) for x in icc[4:8] if x) + ' '
                    profile += ''.join(chr(x) for x in icc[48:56] if x)
            
            ret.update(width=width, height=height,
                       icc_profile=profile,
                       megapixels=width*height/1000000)
            # TODO: check that img.format matches the extension
            return ret
        except:
            msg = _('Error occurred reading the image file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
    
    def process(self, file, meta, max_width=None, max_height=None, **kwargs):
        try:
            if 'icc_profile' not in meta or not meta['icc_profile']:
                # some browsers mess up w/ untagged images - should assume sRGB
                pass # TODO needs more research
#                with Image.open(file.path) as img:
#                    srgb = ImageCms.createProfile('sRGB')
#                    img = ImageCms.profileToProfile(orig, srgb).tobytes()
#                    img.save(file.path, img.format, icc_profile=srgb_profile)
#                    meta['icc_profile'] = ' '
            
            if not max_width and not max_height: return meta
            if meta['width'] <= max_width and meta['height'] <= max_height:
                return meta
            
            with Image.open(file.path) as img:
                img.load()
                profile = img.info.get('icc_profile', '')
                img.thumbnail((max_width, max_height), Image.ANTIALIAS)
                new_img = ImageOps.exif_transpose(img)
                new_width, new_height = new_img.size
                new_img.save(file.path, img.format, icc_profile=profile)
                new_size = os.path.getsize(file.path)
            
            meta['width'], meta['height'] = new_width, new_height
            meta['megapixels'] = new_width * new_height / 1000000
            msg = _('Image was resized to %(width)sx%(height)s.')
            meta['message'] = msg % {'width': new_width, 'height': new_height}
            meta['update_filesize'] = new_size
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
                    profile = img.info.get('icc_profile', '')
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.thumbnail((120, 120), Image.ANTIALIAS)
                    new_img = ImageOps.exif_transpose(img)
                    # TODO: need an alternative name thing
                    outpath = thumbnail_path(file.path)
                    if not os.path.isfile(outpath):
                        new_img.save(outpath, img.format, icc_profile=profile)
            except:
                self.logger.critical('Error generating thumbnail.',
                                     exc_info=True)
    
    def admin_limit_fields(self):
        return ('width', 'height', 'megapixels')
    
    def admin_total_fields(self):
        return ('megapixels',)
    
    def admin_processing_fields(self):
        return ('max_width', 'max_height')
