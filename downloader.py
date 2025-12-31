import os
import yt_dlp
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = 'downloads'

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

class Downloader:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True,
            # Use mobile clients to bypass "Sign in to confirm you’re not a bot"
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],
                },
                'tiktok': {
                    'app_version': '30.0.0', # Mock a recent app version
                }
            },
            # Spoof User-Agent to look like a regular browser
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Force IPv4 as IPv6 is often more restricted
            # TikTok sometimes blocks or has issues with IPv4, so we remove this restriction or make it flexible
            # 'force_ipv4': True, 
            # Force IPv4 explicitly because IPv6 often fails with "getaddrinfo failed" on some networks for TikTok
            'force_ipv4': True,
            'noplaylist': True,
            'socket_timeout': 30,
            # 'http_chunk_size': 10485760, # 10MB - Commented out as it might cause range issues
            'retries': 10,
            'fragment_retries': 10,
            'ignoreerrors': True,
            # Disable concurrent fragments to avoid "Conflicting range" errors on some servers
            'concurrent_fragment_downloads': 1,
        }

    def get_info(self, url):
        """
        Extracts information from the URL without downloading.
        """
        try:
            opts = self.ydl_opts.copy()
            opts['quiet'] = True
            
            # TikTok specific fixes for get_info
            if 'tiktok.com' in url or 'vm.tiktok.com' in url:
                # TikTok often blocks generic User-Agents or IPv6.
                # 'facebookexternalhit' works well for link previews, which we simulate here.
                # Also disabling IPv6 check for this specific request if global force_ipv4 is not enough
                opts['user_agent'] = 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'
                # Some TikTok servers have DNS issues with IPv6 on certain networks
                opts['force_ipv4'] = True 
                
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
        Downloads media from the given URL.
        format_type: 'video' or 'audio'
        quality: 
          - For video: 'best', '1080', '720', '480', '360' (height)
          - For audio: 'best', '320', '192', '128' (bitrate in kbps)
        progress_hook: function to call with progress updates
        """
        try:
            # Create a unique temporary filename template to avoid collisions
            unique_id = str(uuid.uuid4())[:8]
            
            opts = self.ydl_opts.copy()

            if 'tiktok.com' in url or 'vm.tiktok.com' in url:
                 opts['user_agent'] = 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'
                 opts['force_ipv4'] = True
            
            # Add progress hook
            if progress_hook:
                opts['progress_hooks'] = [progress_hook]

            # Configure format based on type and quality
            if format_type == 'audio':
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality if quality != 'best' else '192',
                }]
                opts['outtmpl'] = f'{DOWNLOAD_DIR}/{unique_id}_%(title).50s.%(ext)s'
            else: # video
                # Check if URL is Instagram, which often has single file formats
                is_instagram = 'instagram.com' in url or 'instagr.am' in url
                
                if quality == 'best':
                    if is_instagram:
                         # Instagram often fails with bestvideo+bestaudio, so we fallback to 'best'
                        opts['format'] = 'bestvideo+bestaudio/best'
                    else:
                        opts['format'] = 'bestvideo+bestaudio/best'
                else:
                    # Select best video with height <= quality
                    opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
                
                # For Instagram, if the specific format fails, we want to fallback
                if is_instagram:
                     # Allow fallback to just 'best' if merge fails or formats missing
                     opts['format'] = opts['format'] + '/best'

                opts['merge_output_format'] = 'mp4'
                opts['outtmpl'] = f'{DOWNLOAD_DIR}/{unique_id}_%(title).50s.%(ext)s'

            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"Extracting info for {url}")
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    return {
                        'status': 'error',
                        'message': 'Could not extract information from the URL. The video might be private or unavailable.'
                    }

                # Determine file path
                # yt-dlp might return a list of entries for playlists, we handle single file for now
                if 'entries' in info:
                    # It's a playlist or multi-video link, take the first one
                    info = info['entries'][0]
                
                filename = ydl.prepare_filename(info)
                
                # If the file was merged (e.g. video+audio), the extension might differ from prepared filename
                # We need to find the actual file on disk if the prepared one doesn't exist
                if not os.path.exists(filename):
                    # Try to find a file starting with the same name (ignoring extension)
                    base_name = os.path.splitext(filename)[0]
                    for f in os.listdir(DOWNLOAD_DIR):
                        if f.startswith(os.path.basename(base_name)):
                            filename = os.path.join(DOWNLOAD_DIR, f)
                            break
                
                media_type = 'video'
                if format_type == 'audio':
                    media_type = 'audio'
                # Check if it looks like an image (Pinterest often returns images)
                elif filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
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
