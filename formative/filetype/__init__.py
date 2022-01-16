from django.utils.translation import gettext_lazy as _
import logging

__all__ = ["ImageFile", "DocumentFile", "AudioFile", "VideoFile"]


class FileType:
    types = {}
    extensions = {}
    composite = False
    logger = logging.getLogger('django.request')
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.TYPE:
            cls.types[cls.TYPE] = cls
            for extension in cls.EXTENSIONS:
                cls.extensions[extension] = cls
    
    @classmethod
    def by_type(cls, type):
        return cls.types[type]
    
    @classmethod
    def by_extension(cls, extension):
        if extension in cls.extensions:
            return cls.extensions[extension]
        return None
    
    # at some point, will probably want to load file type options here
    
    def allowed_extensions(self):
        return self.EXTENSIONS
    
    def meta(self, path):
        return {}
    
    def limit_error(self, meta, limits):
        for key, val in limits.items():
            if not (key.startswith('max_') or key.startswith('min_')): continue
            name = key[4:]
            if name == 'filesize' or name not in meta: continue
            v = meta[name]
            
            retname = _(name.replace('_', ' '))
            if key.startswith('max_'):
                if v > val:
                    m = _('Maximum for %(name)s is %(maxval)s. It is %(val)s.')
                    return m % {'name': retname, 'maxval': val, 'val': v}
            else:
                if v < val:
                    m = _('Minimum for %(name)s is %(minval)s. It is %(val)s.')
                    return m % {'name': retname, 'maxval': val, 'val': v}
        
        return None


from .image import ImageFile
from .document import DocumentFile
from .av import AudioFile, VideoFile
