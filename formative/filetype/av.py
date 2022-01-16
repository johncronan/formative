from django.utils.translation import gettext_lazy as _
import ffmpeg

from ..utils import get_file_extension
from . import FileType


class AVFileType(FileType):
    TYPE = None
    
    def meta(self, path):
        try:
            probe = ffmpeg.probe(path)
            streams, msg = probe['streams'], ''
            audio_streams = [ s for s in streams if s['codec_type'] == 'audio' ]
            video_streams = [ s for s in streams if s['codec_type'] == 'video' ]
            ext = get_file_extension(path)
            
            format = probe['format']['format_name']
            if ext == 'mp3':
                if 'mp3' not in format.split(','):
                    return {'error': _('Incorrect format for MP3 '
                                       'file extension.')}
            else:
                if 'mp4' not in format.split(','):
                    return {'error': _('Media container format must be MP4.')}
            
            if len(audio_streams) > 1:
                return {'error': _('File contains more than 1 audio stream.')}
            if len(video_streams) > 1:
                return {'error': _('File contains more than 1 video stream.')}
            ret = {
                'seconds': probe['format']['duration'],
                'bit_rate': probe['format']['bit_rate']
            }
            
            if audio_streams: ret.update(self.audio_meta(audio_streams[0], ext))
            if 'error' in ret: return ret
            
            if video_streams: ret.update(self.video_meta(video_streams[0], ext))
            if 'error' in ret: return ret
            
            if not audio_streams and not video_streams: return self.no_stream()
            return ret
        
        except:
            if self.TYPE == 'audio':
                msg = _('Error occurred processing the audio file.')
            else: msg = _('Error occurred processing the video file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}


class AudioFile(AVFileType):
    TYPE = 'audio'
    EXTENSIONS = ('mp3', 'm4a')
    
    def no_stream(self):
        return {'error': _('No audio stream present in the audio file.')}
    
    def video_meta(self, stream, extension):
        if 'attached_pic' in stream['disposition']:
            if stream['disposition']['attached_pic']: return {}
        
        return {'error': _('Video stream present in the audio file.')}
    
    def audio_meta(self, stream, extension):
        codec = stream['codec_name']
        msg = _('Audio codec must be MP3. It is %(codec)s')
        if extension == 'mp3' and codec != extension:
            return {'error': msg % {'codec': codec}}
        if extension != 'mp3' and codec not in ('mp3', 'aac'):
            return {'error': msg % {'codec': codec}}
        
        return {
            'audio_codec': codec,
            'audio_bitrate': stream['bit_rate'],
            'audio_samplerate': stream['sample_rate'],
            'audio_channels': stream['channels']
        }


class VideoFile(AudioFile):
    TYPE = 'video'
    EXTENSIONS = ('mp4', 'm4v')
    
    def no_stream(self):
        return {'error': _('No video stream present in the video file.')}

    def video_meta(self, stream, extension):
        codec = stream['codec_name']
        if codec != 'h264':
            msg = _('Video codec must be H.264 (aka AVC). It is %(codec)s.')
            return {'error': msg % {'codec': codec}}
        
        if 'frame_rate' in stream: frame_rate = stream['frame_rate']
        else: frame_rate = stream['avg_frame_rate']
        divisor = float(frame_rate.split('/')[1])
        if not divisor:
            return {'error': _('Video stream has an invalid frame rate.')}
        
        return {
            'video_codec': codec,
            'video_bitrate': stream['bit_rate'],
            'video_framerate': float(frame_rate.split('/')[0]) / divisor,
            'video_height': stream['height'],
            'video_width': stream['width']
        }
