from django.utils.translation import gettext_lazy as _
import ffmpeg
import os

from ..utils import get_file_extension, thumbnail_path, subtitle_path
from . import FileType


class AVFileType(FileType):
    TYPE = None
    
    def meta(self, path):
        ret = super().meta(path)
        
        try:
            probe = ffmpeg.probe(path)
            streams, msg = probe['streams'], ''
            audio_streams = [ s for s in streams if s['codec_type'] == 'audio' ]
            video_streams = [ s for s in streams if s['codec_type'] == 'video' ]
            subtitles = [ s for s in streams if s['codec_type'] == 'subtitle' ]
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
            ret.update(seconds=float(probe['format']['duration']),
                       bit_rate=float(probe['format']['bit_rate']))
            
            if audio_streams: ret.update(self.audio_meta(audio_streams[0], ext))
            if 'error' in ret: return ret
            
            if video_streams: ret.update(self.video_meta(video_streams[0], ext))
            if 'error' in ret: return ret
            
            if subtitles and video_streams:
                ret.update(self.subtitle_meta(subtitles, ext))
                if 'error' in ret: return ret
            
            if not audio_streams and not video_streams: return self.no_stream()
            if ext in VideoFile.EXTENSIONS and not video_streams:
                return self.no_stream()
            if ext in AudioFile.EXTENSIONS and not audio_streams:
                return self.no_stream()
            
            return ret
        
        except:
            if self.TYPE == 'audio':
                msg = _('Error occurred reading the audio file.')
            else: msg = _('Error occurred reading the video file.')
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
        msg = _('Audio codec must be %(req)s. It is %(codec)s')
        if extension == 'mp3' and codec != extension:
            return {'error': msg % {'req': 'mp3', 'codec': codec}}
        if extension == 'm4a' and codec != 'aac':
            return {'error': msg % {'req': 'aac', 'codec': codec}}
        
        return {
            'audio_codec': codec,
            'audio_bitrate': float(stream['bit_rate']),
            'audio_samplerate': float(stream['sample_rate']),
            'audio_channels': stream['channels']
        }
    
    def subtitle_meta(self, stream, extension):
        return {}
    
    def admin_limit_fields(self):
        return ('seconds', 'bitrate', 'audio_bitrate', 'audio_samplerate',
                'audio_channels')


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
            'video_bitrate': float(stream['bit_rate']),
            'video_framerate': float(frame_rate.split('/')[0]) / divisor,
            'video_height': stream['height'],
            'video_width': stream['width']
        }
    
    def subtitle_meta(self, streams, extension):
        subs = []
        for i, stream in enumerate(streams):
            codec = stream['codec_name']
            if codec != 'mov_text':
                msg = _('Subtitle format must be mov_text (aka MP4TT). '
                        'It is %(codec)s.')
                return {'error': msg % {'codec': codec}}
        
            lang = 'und'
            if 'language' in stream['tags']: lang = stream['tags']['language']
            
            default = False
            if 'disposition' in stream and 'default' in stream['disposition']:
                default = bool(stream['disposition']['default'])
            
            subs.append((i, lang, default))
        
        return { 'subtitle_streams': subs }
    
    def process(self, file, meta, extract_captions=True, **kwargs):
        if not extract_captions or 'subtitle_streams' not in meta: return meta
        
        try:
            v, subs = ffmpeg.input(file.path), []
            for idx, lang, default in meta['subtitle_streams']:
                filename = subtitle_path(file.path, lang)
                v = v.output(filename, map=f'0:s:{idx}')
                relpath = subtitle_path(file.name, lang)
                
                desc = {'language': lang, 'file': relpath}
                if default: desc['default'] = True
                subs.append(desc)
            v.run()
            
            meta['subtitles'] = subs
            meta.pop('subtitle_streams')
            msg = _('Extracted %(num)d embedded subtitle track(s).')
            meta['message'] = msg % {'num': len(subs)}
            
            return meta
        except:
            msg = _('Error occurred processing the video file.')
            self.logger.critical(msg, exc_info=True)
            return {'error': msg}
    
    def submitted(self, items):
        for item in items:
            file = item._file
            
            try:
                v = ffmpeg.input(file.path, ss=item._filemeta['seconds']/4)
                outpath = thumbnail_path(file.path, ext='jpg')
                if not os.path.isfile(outpath):
                    v.filter('scale', 120, -1).output(outpath, vframes=1).run()
            except:
                self.logger.critical('Error generating video thumbnail.',
                                     exc_info=True)
    
    def admin_limit_fields(self):
        return ('seconds', 'bitrate', 'video_bitrate', 'video_framerate',
                'video_width', 'video_height')
    
    def admin_total_fields(self):
        return ('seconds',)
    
    def artifact_url(self, name, url):
        if not name.startswith('subtitles_'): return None
        return subtitle_path(url, name[len('subtitles_'):])
