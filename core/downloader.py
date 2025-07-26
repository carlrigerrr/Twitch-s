import subprocess
import time
import os
from config import DOWNLOAD_TIMEOUT

class Downloader:
    def __init__(self):
        pass
    
    def download_clip(self, clip_data, save_path, log_func=None, stop_check_func=None):
        """Download a single clip with better error handling"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            if stop_check_func and stop_check_func():
                return False
                
            try:
                if log_func:
                    log_func(f"⬇️ Downloading: {clip_data['title']}")
                
                # Use streamlink to get the best quality
                cmd = [
                    'streamlink',
                    clip_data['url'],
                    'best',
                    '-o', save_path,
                    '--force'
                ]
                
                # Add timeout to streamlink command
                result = subprocess.run(cmd, capture_output=True, text=True, 
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                      timeout=DOWNLOAD_TIMEOUT)
                
                if result.returncode == 0:
                    if log_func:
                        log_func(f"✅ Downloaded: {clip_data['title']}")
                    return True
                else:
                    retry_count += 1
                    if log_func:
                        log_func(f"❌ Download failed (attempt {retry_count}/{max_retries}): {result.stderr}")
                    if retry_count < max_retries:
                        time.sleep(5)  # Wait before retry
                        
            except subprocess.TimeoutExpired:
                retry_count += 1
                if log_func:
                    log_func(f"⚠️ Download timeout (attempt {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    time.sleep(5)
            except Exception as e:
                retry_count += 1
                if log_func:
                    log_func(f"❌ Error downloading (attempt {retry_count}/{max_retries}): {str(e)}")
                if retry_count < max_retries:
                    time.sleep(5)
        
        return False
    
    def check_streamlink(self):
        """Check if streamlink is installed"""
        try:
            subprocess.run(['streamlink', '--version'], capture_output=True, check=True,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return True
        except:
            return False
    
    def check_ffmpeg(self):
        """Check if ffmpeg is installed"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return True
        except:
            return False