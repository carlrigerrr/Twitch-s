import requests
import re
from datetime import datetime, timedelta
from utils.helpers import check_internet_connection
from config import API_TIMEOUT

class TwitchAPI:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        
    def authenticate(self):
        """Get permission from Twitch to use their API"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not check_internet_connection():
                    return False, "No internet connection"
                
                auth_url = "https://id.twitch.tv/oauth2/token"
                data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials'
                }
                
                response = requests.post(auth_url, data=data, timeout=10)
                if response.status_code == 200:
                    self.access_token = response.json()['access_token']
                    return True, "Connected to Twitch!"
                else:
                    return False, "Invalid credentials"
                    
            except requests.exceptions.Timeout:
                retry_count += 1
                if retry_count >= max_retries:
                    return False, "Connection timeout"
            except Exception as e:
                return False, str(e)
        
        return False, "Max retries exceeded"
    
    def get_game_id(self, game_url):
        """Figure out which game we're looking for"""
        try:
            match = re.search(r'/category/([^/]+)', game_url)
            if not match:
                return None, None
            
            game_name = match.group(1).replace('-', ' ')
            
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(
                f"https://api.twitch.tv/helix/games",
                headers=headers,
                params={'name': game_name},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    game_info = data['data'][0]
                    return game_info['id'], game_info['name']
            return None, None
        except Exception as e:
            return None, None
    
    def get_broadcaster_language(self, broadcaster_id):
        """Get the language of a single broadcaster using channels endpoint"""
        try:
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(
                f"https://api.twitch.tv/helix/channels",
                headers=headers,
                params={'broadcaster_id': broadcaster_id},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    channel_info = data['data'][0]
                    return channel_info.get('broadcaster_language', '')
            return ''
        except:
            return ''
    
    def get_clips(self, game_id, game_name, min_views, max_views, days_back, 
                  clip_count, language_code, min_duration=None, max_duration=None,
                  check_downloaded_func=None, log_func=None, stop_check_func=None):
        """Find clips that match criteria with improved language detection"""
        try:
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            params = {
                'game_id': game_id,
                'first': 100,
                'started_at': start_date.isoformat() + 'Z',
                'ended_at': end_date.isoformat() + 'Z'
            }
            
            all_clips = []
            cursor = None
            broadcaster_cache = {}
            
            total_checked = 0
            filtered_by_views = 0
            filtered_by_language = 0
            filtered_by_duration = 0
            already_downloaded = 0
            
            max_iterations = 50
            iterations = 0
            
            # For English, use smart detection keywords
            english_indicators = [
                'the', 'and', 'for', 'with', 'this', 'that', 'what',
                'insane', 'crazy', 'best', 'epic', 'clutch', 'win',
                'fail', 'funny', 'moment', 'play', 'game', 'vs',
                'how', 'why', 'when', 'first', 'last', 'new', 'old',
                'my', 'me', 'i', 'you', 'he', 'she', 'we', 'they',
                'is', 'was', 'are', 'were', 'have', 'has', 'had',
                'do', 'does', 'did', 'will', 'would', 'could', 'should',
                'get', 'got', 'take', 'took', 'make', 'made', 'go', 'went'
            ]
            
            if log_func:
                if language_code == 'all':
                    log_func(f"🌍 Language filter: All Languages (no filtering)")
                elif language_code == 'en':
                    log_func(f"🇺🇸 Language filter: English (using smart detection + API)")
                elif language_code == '':
                    log_func(f"❓ Language filter: Unknown/Not Set")
                elif language_code == 'other':
                    log_func(f"🌐 Language filter: Other Languages")
                else:
                    log_func(f"🌍 Language filter: {language_code} (using API)")
            
            while len(all_clips) < clip_count and iterations < max_iterations:
                if stop_check_func and stop_check_func():
                    break
                    
                iterations += 1
                
                if cursor:
                    params['after'] = cursor
                
                try:
                    response = requests.get(
                        "https://api.twitch.tv/helix/clips",
                        headers=headers,
                        params=params,
                        timeout=API_TIMEOUT
                    )
                except requests.exceptions.Timeout:
                    if log_func:
                        log_func("⚠️ API timeout. Retrying...")
                    continue
                except requests.exceptions.ConnectionError:
                    if log_func:
                        log_func("⚠️ Connection error. Check your internet.")
                    if not check_internet_connection():
                        if log_func:
                            log_func("❌ No internet connection!")
                        break
                    continue
                
                if response.status_code != 200:
                    if log_func:
                        log_func(f"❌ API Error: {response.status_code}")
                    break
                
                data = response.json()
                clips = data.get('data', [])
                
                if not clips:
                    if log_func:
                        log_func("   No more clips available from Twitch")
                    break
                
                if log_func:
                    log_func(f"   Checking batch of {len(clips)} clips...")
                
                for clip in clips:
                    if stop_check_func and stop_check_func():
                        break
                        
                    total_checked += 1
                    view_count = clip['view_count']
                    duration = clip['duration']
                    clip_id = clip['id']
                    
                    # Check if already downloaded
                    if check_downloaded_func and check_downloaded_func(clip_id):
                        already_downloaded += 1
                        continue
                    
                    # Check views
                    if view_count < min_views:
                        filtered_by_views += 1
                        continue
                    if max_views and view_count > max_views:
                        filtered_by_views += 1
                        continue
                    
                    # Check duration
                    if min_duration is not None and max_duration is not None:
                        if duration < min_duration or duration > max_duration:
                            filtered_by_duration += 1
                            continue
                    
                    # IMPROVED Language filtering
                    if language_code != 'all':
                        broadcaster_id = clip['broadcaster_id']
                        clip_title = clip['title'].lower()
                        broadcaster_name = clip['broadcaster_name']
                        
                        # Get broadcaster language (with caching)
                        if broadcaster_id not in broadcaster_cache:
                            broadcaster_lang = self.get_broadcaster_language(broadcaster_id)
                            broadcaster_cache[broadcaster_id] = broadcaster_lang
                            if len(broadcaster_cache) <= 5 and log_func:
                                lang_display = broadcaster_lang if broadcaster_lang else 'Not Set'
                                log_func(f"   📡 {broadcaster_name}: language = '{lang_display}'")
                        else:
                            broadcaster_lang = broadcaster_cache[broadcaster_id]
                        
                        language_match = False
                        
                        if language_code == 'en':  # English - Use hybrid approach
                            # Method 1: Check broadcaster language
                            if broadcaster_lang == 'en':
                                language_match = True
                            else:
                                # Method 2: Smart title detection for English
                                title_words = clip_title.split()
                                english_word_count = sum(1 for word in title_words 
                                                       if word.strip('.,!?()[]{}') in english_indicators)
                                
                                # If title has English words OR broadcaster didn't set language
                                if english_word_count >= 2 or broadcaster_lang == '':
                                    language_match = True
                        
                        elif language_code == '':  # Unknown/Not Set
                            language_match = (broadcaster_lang == '' or broadcaster_lang is None)
                        
                        elif language_code == 'other':  # Other Languages
                            main_langs = ['en', 'es', 'pt', 'fr', 'de', 'it', 'ru', 'ko', 'ja', 'zh']
                            language_match = (broadcaster_lang != '' and broadcaster_lang not in main_langs)
                        
                        else:  # Specific language
                            language_match = (broadcaster_lang == language_code)
                        
                        if not language_match:
                            filtered_by_language += 1
                            continue
                        
                        # Log successful matches for first few clips
                        if len(all_clips) < 3 and log_func:
                            method = ""
                            if language_code == 'en':
                                if broadcaster_lang == 'en':
                                    method = " (API match)"
                                else:
                                    method = " (title detection)"
                            lang_display = broadcaster_lang if broadcaster_lang else 'Not Set'
                            log_func(f"   ✅ Language match: {broadcaster_name} = '{lang_display}'{method}")
                    
                    # Clip passed all filters
                    all_clips.append(clip)
                
                pagination = data.get('pagination', {})
                cursor = pagination.get('cursor')
                
                if not cursor:
                    if log_func:
                        log_func("   No more pages available")
                    break
                
                if log_func:
                    log_func(f"   Progress: {len(all_clips)} new clips found, {total_checked} checked total")
            
            # Final statistics
            if log_func:
                log_func(f"\n📊 Search Summary:")
                log_func(f"   Total clips checked: {total_checked}")
                log_func(f"   Filtered by views: {filtered_by_views}")
                log_func(f"   Filtered by duration: {filtered_by_duration}")
                log_func(f"   Filtered by language: {filtered_by_language}")
                if check_downloaded_func:
                    log_func(f"   Already downloaded: {already_downloaded}")
                log_func(f"   Final clips matching criteria: {len(all_clips)}")
                
                # Show language distribution if we collected it
                if broadcaster_cache:
                    lang_counts = {}
                    for lang in broadcaster_cache.values():
                        lang_key = lang if lang else 'Not Set'
                        lang_counts[lang_key] = lang_counts.get(lang_key, 0) + 1
                    
                    log_func(f"\n🌍 Language distribution found:")
                    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                        log_func(f"   '{lang}': {count} streamers")
                
                # Helpful tips
                if language_code != 'all' and len(all_clips) == 0:
                    log_func("\n💡 Tips to find more clips:")
                    log_func("   • Try 'All Languages' first")
                    log_func("   • Try 'Unknown/Not Set' (many streamers don't set language)")
                    log_func("   • Lower the minimum views requirement")
                    log_func("   • Increase days back to search")
            
            all_clips.sort(key=lambda x: x['view_count'], reverse=True)
            return all_clips[:clip_count], game_name
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Error getting clips: {str(e)}")
            return [], game_name