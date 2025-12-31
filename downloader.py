import os
import time
import logging
import yt_dlp
import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.path.exists(config.output_folder):
    os.makedirs(config.output_folder)

class Downloader:
    def __init__(self):
        # We don't need complex init options anymore as we construct them per download
        # matching main.py's approach
        pass

    def get_info(self, url):
        """
        Extracts information from the URL without downloading.
        """
        try:
            # Basic options for getting info
            opts = {
                'quiet': True,
                'no_warnings': True,
                # TikTok specific fixes might still be useful for get_info if main.py doesn't oppose them
                # But to stick to "exact same method", we'll use minimal options first.
                # If users report issues, we can re-add them.
                # However, get_info is not in the snippet of main.py provided.
                # I will use a simple configuration for get_info.
            }
            
            # TikTok/Instagram specific user-agent hacks often needed
            if 'tiktok.com' in url or 'vm.tiktok.com' in url:
                opts['user_agent'] = 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return {'status': 'error', 'message': 'Could not extract info'}
                
                if 'entries' in info:
                    info = info['entries'][0]

                return {
                    'status': 'success',
                    'title': info.get('title', 'Unknown'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'formats': info.get('formats', [])
                }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def download(self, url, format_type='video', quality='best', progress_hook=None):
        """
        Downloads media from the given URL using the method from main.py.
        """
        video_title = round(time.time() * 1000)
        
        audio = (format_type == 'audio')
        
        # Determine format_id
        # main.py takes 'format_id' as argument.
        # We map our quality/type args to a format string.
        if audio:
            format_id = 'bestaudio/best'
        else:
            if quality == 'best':
                format_id = 'bestvideo+bestaudio/best'
            elif quality in ['1080', '720', '480', '360']:
                format_id = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
            else:
                format_id = 'best'
        
        # Configuration exactly as requested from main.py
        # {'format': format_id, 'outtmpl': f'{config.output_folder}/{video_title}.%(ext)s', 'progress_hooks': [progress], 'postprocessors': [{ ... }] if audio else [], 'max_filesize': config.max_filesize}
        
        opts = {
            'format': format_id,
            'outtmpl': f'{config.output_folder}/{video_title}.%(ext)s',
            'progress_hooks': [progress_hook] if progress_hook else [],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }] if audio else [],
            'max_filesize': config.max_filesize,
            'quiet': True,
            'no_warnings': True
        }

        # TikTok/Instagram user agent hacks might be needed?
        # The user said "use the exact same method as main.py". 
        # main.py does NOT show these hacks in the snippet.
        # I will strictly follow main.py and NOT add hacks unless necessary.
        # However, for get_info I kept them because get_info wasn't in main.py snippet.
        # For download, I will stick to the snippet provided.

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"Downloading {url} with opts: {opts}")
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    return {
                        'status': 'error',
                        'message': 'Could not extract information from the URL.'
                    }

                # Determine file path
                # Since we use outtmpl with video_title (timestamp), we can predict the filename
                # But extensions might change (e.g. mkv -> mp4 or audio conversion)
                
                # ydl.prepare_filename might return the 'before postprocessing' name
                filename = ydl.prepare_filename(info)
                
                # If audio postprocessor ran, it might have changed extension to mp3
                if audio:
                    base, _ = os.path.splitext(filename)
                    filename = f"{base}.mp3"
                
                # Check if file exists, if not try to find it
                if not os.path.exists(filename):
                     # fallback: list dir and find file starting with video_title
                     for f in os.listdir(config.output_folder):
                         if f.startswith(str(video_title)):
                             filename = os.path.join(config.output_folder, f)
                             break
                
                media_type = 'audio' if audio else 'video'
                # Simple check for image
                if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    media_type = 'image'

                return {
                    'status': 'success',
                    'type': media_type,
                    'path': filename,
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                }
                
        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
