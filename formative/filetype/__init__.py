
__all__ = ["ImageFile", "DocumentFile"]


class FileType:
    types = {}
    extensions = {}
    composite = False
    
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
    

from .image import ImageFile
from .document import DocumentFile
