import os
import json
import pickle
import time
import shutil
from datetime import datetime, timedelta
import requests
from config import YOUTUBE_SCOPES, YOUTUBE_CATEGORY_GAMING, YOUTUBE_CREDENTIALS_DIR

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

class YouTubeHandler:
    def __init__(self):
        self.channels = []
        self.credentials_dir = YOUTUBE_CREDENTIALS_DIR
        os.makedirs(self.credentials_dir, exist_ok=True)
        
    def is_available(self):
        """Check if YouTube libraries are available"""
        return YOUTUBE_AVAILABLE
    
    def save_credential_info(self, safe_name, display_name):
        """Save credential information"""
        cred_file = os.path.join(self.credentials_dir, "credentials_info.json")
        
        try:
            if os.path.exists(cred_file):
                with open(cred_file, 'r') as f:
                    cred_info = json.load(f)
            else:
                cred_info = []
            
            # Check if already exists
            existing = next((c for c in cred_info if c['safe_name'] == safe_name), None)
            if existing:
                existing['display_name'] = display_name
            else:
                cred_info.append({
                    'safe_name': safe_name,
                    'display_name': display_name,
                    'channels': 0,
                    'created': datetime.now().isoformat()
                })
            
            with open(cred_file, 'w') as f:
                json.dump(cred_info, f, indent=2)
                
        except Exception:
            pass
    
    def load_credential_info(self):
        """Load credential information"""
        cred_file = os.path.join(self.credentials_dir, "credentials_info.json")
        
        if os.path.exists(cred_file):
            try:
                with open(cred_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Try to detect existing credentials
        cred_info = []
        for file in os.listdir(self.credentials_dir):
            if file.startswith("client_secret_") and file.endswith(".json"):
                safe_name = file.replace("client_secret_", "").replace(".json", "")
                display_name = safe_name.replace("_", " ").title()
                cred_info.append({
                    'safe_name': safe_name,
                    'display_name': display_name,
                    'channels': 0
                })
        
        # Also check for old single credential
        old_path = os.path.join(self.credentials_dir, "client_secret.json")
        if os.path.exists(old_path):
            cred_info.append({
                'safe_name': 'default',
                'display_name': 'Default Credentials',
                'channels': 0
            })
            # Rename it to new format
            new_path = os.path.join(self.credentials_dir, "client_secret_default.json")
            shutil.move(old_path, new_path)
        
        return cred_info
    
    def save_all_credential_info(self, cred_info):
        """Save all credential information"""
        cred_file = os.path.join(self.credentials_dir, "credentials_info.json")
        with open(cred_file, 'w') as f:
            json.dump(cred_info, f, indent=2)
    
    def authenticate_channel(self, client_secret_path, channel_name, credential_name, 
                           credential_display, auth_mode='auto'):
        """Authenticate a YouTube channel"""
        if not YOUTUBE_AVAILABLE:
            return None, "YouTube libraries not available"
        
        try:
            token_file = os.path.join(self.credentials_dir, 
                                    f"token_{credential_name}_{channel_name.replace(' ', '_')}.pickle")
            
            creds = None
            
            # Token file stores the user's access and refresh tokens
            if os.path.exists(token_file):
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)
            
            # If there are no (valid) credentials available, let the user log in
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_path, YOUTUBE_SCOPES)
                    
                    if auth_mode == 'auto':
                        creds = flow.run_local_server(port=0)
                    else:
                        # Manual mode
                        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                        auth_url, _ = flow.authorization_url(prompt='consent')
                        return {'type': 'manual', 'flow': flow, 'auth_url': auth_url, 
                               'token_file': token_file, 'channel_name': channel_name,
                               'credential_name': credential_name, 
                               'credential_display': credential_display}
                
                # Save the credentials for the next run
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
            
            # Build YouTube service
            youtube = build('youtube', 'v3', credentials=creds)
            
            # Get channel info
            request = youtube.channels().list(
                part="snippet",
                mine=True
            )
            response = request.execute()
            
            if response['items']:
                channel_info = response['items'][0]['snippet']
                channel_id = response['items'][0]['id']
                
                # Save channel info
                channel_data = {
                    'name': channel_name,
                    'channel_id': channel_id,
                    'channel_title': channel_info['title'],
                    'token_file': token_file,
                    'credentials': creds,
                    'credential_name': credential_name,
                    'credential_display': credential_display
                }
                
                return channel_data, None
            else:
                return None, "Could not retrieve channel information"
                
        except Exception as e:
            return None, str(e)
    
    def complete_manual_auth(self, auth_data, auth_code):
        """Complete manual authentication with auth code"""
        try:
            flow = auth_data['flow']
            
            # Exchange code for credentials
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            
            # Save the credentials
            with open(auth_data['token_file'], 'wb') as token:
                pickle.dump(creds, token)
            
            # Build YouTube service
            youtube = build('youtube', 'v3', credentials=creds)
            
            # Get channel info
            request = youtube.channels().list(
                part="snippet",
                mine=True
            )
            response = request.execute()
            
            if response['items']:
                channel_info = response['items'][0]['snippet']
                channel_id = response['items'][0]['id']
                
                # Save channel info
                channel_data = {
                    'name': auth_data['channel_name'],
                    'channel_id': channel_id,
                    'channel_title': channel_info['title'],
                    'token_file': auth_data['token_file'],
                    'credentials': creds,
                    'credential_name': auth_data['credential_name'],
                    'credential_display': auth_data['credential_display']
                }
                
                return channel_data, None
            else:
                return None, "Could not retrieve channel information"
                
        except Exception as e:
            return None, str(e)
    
    def save_channels(self, channels):
        """Save channel information (without credentials)"""
        channels_file = os.path.join(self.credentials_dir, "channels.json")
        
        try:
            # Save only non-sensitive data
            channels_data = []
            for channel in channels:
                channel_info = {
                    'name': channel['name'],
                    'channel_id': channel['channel_id'],
                    'channel_title': channel['channel_title'],
                    'token_file': channel['token_file']
                }
                # Add credential info if present
                if 'credential_name' in channel:
                    channel_info['credential_name'] = channel['credential_name']
                if 'credential_display' in channel:
                    channel_info['credential_display'] = channel['credential_display']
                channels_data.append(channel_info)
            
            with open(channels_file, 'w') as f:
                json.dump(channels_data, f, indent=2)
        except Exception:
            pass
    
    def load_channels(self):
        """Load saved YouTube channels"""
        channels_file = os.path.join(self.credentials_dir, "channels.json")
        loaded_channels = []
        
        if os.path.exists(channels_file):
            try:
                with open(channels_file, 'r') as f:
                    channels_data = json.load(f)
                
                for channel_data in channels_data:
                    # Load credentials from token file
                    if os.path.exists(channel_data['token_file']):
                        try:
                            with open(channel_data['token_file'], 'rb') as token:
                                creds = pickle.load(token)
                            
                            channel_data['credentials'] = creds
                            loaded_channels.append(channel_data)
                        except:
                            pass
                
            except Exception:
                pass
        
        return loaded_channels
    
    def upload_video(self, channel, video_path, title, description, privacy, 
                    scheduled, schedule_time, tags=None, log_func=None):
        """Upload a video to YouTube with better error handling"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Build YouTube service with channel credentials
                youtube = build('youtube', 'v3', credentials=channel['credentials'])
                
                # Video metadata
                body = {
                    'snippet': {
                        'title': title,
                        'description': description,
                        'tags': tags or ['gaming', 'twitch', 'clips'],
                        'categoryId': YOUTUBE_CATEGORY_GAMING
                    },
                    'status': {
                        'privacyStatus': privacy
                    }
                }
                
                # Add schedule time if provided
                if scheduled and schedule_time:
                    try:
                        # Parse schedule time
                        schedule_dt = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M")
                        # Convert to ISO format with timezone
                        body['status']['publishAt'] = schedule_dt.isoformat() + 'Z'
                        body['status']['privacyStatus'] = 'private'  # Must be private for scheduling
                    except:
                        if log_func:
                            log_func(f"⚠️ Invalid schedule time format, uploading immediately")
                
                # Call the API's videos.insert method
                insert_request = youtube.videos().insert(
                    part=",".join(body.keys()),
                    body=body,
                    media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
                )
                
                # Execute upload
                response = None
                error = None
                retry = 0
                
                while response is None:
                    try:
                        status, response = insert_request.next_chunk()
                        if status:
                            percent = int(status.progress() * 100)
                            if log_func:
                                log_func(f"   Upload progress: {percent}%")
                    except HttpError as e:
                        if e.resp.status in [500, 502, 503, 504]:
                            # Retry on server errors
                            error = f"Server error: {e}"
                            retry += 1
                            if retry > 3:
                                raise
                            time.sleep(2 ** retry)
                        else:
                            raise
                    except Exception as e:
                        error = f"An error occurred: {e}"
                        raise
                
                if response is not None:
                    video_id = response['id']
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    if log_func:
                        log_func(f"✅ Upload successful! Video URL: {video_url}")
                    return video_id
                else:
                    if log_func:
                        log_func(f"❌ Upload failed: {error}")
                    return None
                    
            except requests.exceptions.ConnectionError:
                retry_count += 1
                if log_func:
                    log_func(f"⚠️ Connection error (attempt {retry_count}/{max_retries}). Waiting 30 seconds...")
                time.sleep(30)
            except Exception as e:
                if log_func:
                    log_func(f"❌ YouTube upload error: {str(e)}")
                
                # Check if it's a quota exceeded error
                if "quota" in str(e).lower():
                    if log_func:
                        log_func("⚠️ YouTube quota exceeded for today. Try again tomorrow.")
                    return None
                
                retry_count += 1
                if retry_count < max_retries:
                    if log_func:
                        log_func(f"⚠️ Retrying upload (attempt {retry_count}/{max_retries})...")
                    time.sleep(10)
                else:
                    return None
        
        return None