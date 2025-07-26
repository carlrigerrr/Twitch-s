import re
import os
import socket
import sys
from datetime import datetime, timedelta
import calendar
import urllib.request
import urllib.error

def sanitize_filename(filename):
    """Remove invalid characters from filename with Unicode safety"""
    if not filename:
        return "unnamed_file"
    
    try:
        # Convert to string if needed
        if not isinstance(filename, str):
            filename = str(filename)
        
        # Replace invalid characters with underscores
        # Windows invalid chars: < > : " / \ | ? * and control chars (0-31)
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # Remove excessive whitespace and replace with single spaces
        sanitized = re.sub(r'\s+', ' ', sanitized.strip())
        
        # Handle reserved Windows names
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        name_without_ext = os.path.splitext(sanitized)[0].upper()
        if name_without_ext in reserved_names:
            sanitized = f"_{sanitized}"
        
        # Ensure filename isn't too long (255 chars is typical limit)
        if len(sanitized) > 200:  # Leave room for extension and path
            sanitized = sanitized[:200]
        
        # Ensure filename doesn't end with period or space (Windows issue)
        sanitized = sanitized.rstrip('. ')
        
        # If filename becomes empty, provide default
        if not sanitized:
            sanitized = "unnamed_file"
        
        return sanitized
        
    except Exception as e:
        # If anything goes wrong, return a safe default
        return f"file_{int(datetime.now().timestamp())}"

def safe_file_operations():
    """Set up safe file operations for Unicode handling"""
    try:
        # Ensure UTF-8 encoding for file operations
        if sys.platform.startswith('win'):
            # Windows specific Unicode handling
            import locale
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except:
                try:
                    locale.setlocale(locale.LC_ALL, '')
                except:
                    pass  # Use system default
        
        # Set environment variables for consistent encoding
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        
    except Exception:
        pass  # Continue if setup fails

def check_internet_connection():
    """Check if internet connection is available using multiple methods with timeout handling"""
    # Method 1: Try to connect to multiple DNS servers
    dns_servers = [
        ("8.8.8.8", 53),      # Google DNS
        ("1.1.1.1", 53),      # Cloudflare DNS
        ("208.67.222.222", 53), # OpenDNS
    ]
    
    for server, port in dns_servers:
        try:
            socket.create_connection((server, port), timeout=5)  # Increased timeout
            return True
        except (socket.error, socket.timeout, OSError):
            continue
    
    # Method 2: Try HTTP connection to reliable sites
    test_urls = [
        "http://www.google.com",
        "http://www.cloudflare.com",
        "http://www.microsoft.com",
        "https://api.twitch.tv"  # Since we're using Twitch API anyway
    ]
    
    for url in test_urls:
        try:
            # Create request with timeout and safe headers
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout):
            continue
        except Exception:
            continue
    
    # Method 3: Try to resolve a hostname
    try:
        socket.gethostbyname("www.google.com")
        return True
    except (socket.gaierror, OSError):
        pass
    
    # If all methods fail, assume no internet
    return False

def convert_12h_to_24h(time_12h):
    """Convert 12-hour format to 24-hour format with improved parsing"""
    try:
        time_str = time_12h.strip()
        
        if not time_str:
            return None
        
        # Normalize spacing around AM/PM
        time_str = re.sub(r'\s*(AM|PM|am|pm)\s*$', r' \1', time_str, flags=re.IGNORECASE)
        time_str = time_str.strip()
        
        # Try to parse different formats
        formats_to_try = [
            "%I:%M %p",     # 12:30 PM
            "%I:%M%p",      # 12:30PM
            "%I %p",        # 12 PM
            "%I%p",         # 12PM
            "%I:%M %P",     # 12:30 pm (lowercase)
            "%I:%M%P",      # 12:30pm (lowercase)
        ]
        
        for fmt in formats_to_try:
            try:
                time_obj = datetime.strptime(time_str.upper(), fmt.upper())
                return time_obj.strftime("%H:%M")
            except ValueError:
                continue
        
        # Special handling for times like "10:00 AM" with manual parsing
        match = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', time_str, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            am_pm = match.group(3).upper()
            
            if 1 <= hour <= 12 and 0 <= minute <= 59:
                if am_pm == 'PM' and hour != 12:
                    hour += 12
                elif am_pm == 'AM' and hour == 12:
                    hour = 0
                
                return f"{hour:02d}:{minute:02d}"
        
        # Handle simple hour format like "2 PM" or "14"
        match = re.match(r'^(\d{1,2})\s*(AM|PM)?$', time_str, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            am_pm = match.group(2)
            
            if am_pm:
                am_pm = am_pm.upper()
                if 1 <= hour <= 12:
                    if am_pm == 'PM' and hour != 12:
                        hour += 12
                    elif am_pm == 'AM' and hour == 12:
                        hour = 0
                    return f"{hour:02d}:00"
            else:
                # No AM/PM specified, assume 24-hour format if hour > 12
                if 0 <= hour <= 23:
                    return f"{hour:02d}:00"
        
        return None
        
    except Exception:
        return None

def convert_24h_to_12h(time_24h):
    """Convert 24-hour format to 12-hour format with error handling"""
    try:
        if not time_24h:
            return time_24h
        
        # Handle different input formats
        if isinstance(time_24h, str) and ':' in time_24h:
            time_obj = datetime.strptime(time_24h, "%H:%M")
            return time_obj.strftime("%I:%M %p").lstrip('0')  # Remove leading zero
        else:
            return time_24h
    except Exception:
        return time_24h  # Return original if conversion fails

def get_ordered_days_from_today():
    """Get days ordered starting from today"""
    try:
        days = list(calendar.day_name)
        current_day = datetime.now().strftime('%A')
        today_index = days.index(current_day)
        
        # Reorder days starting from today
        ordered_days = days[today_index:] + days[:today_index]
        return ordered_days
    except Exception:
        # Fallback to standard order if anything goes wrong
        return list(calendar.day_name)

def calculate_time_until(target_day, target_time):
    """Calculate time until a specific day and time with improved error handling"""
    try:
        now = datetime.now()
        current_day = now.strftime('%A')
        
        # Get days in order
        days = list(calendar.day_name)
        current_day_index = days.index(current_day)
        target_day_index = days.index(target_day)
        
        # Calculate days until target
        if target_day_index >= current_day_index:
            days_ahead = target_day_index - current_day_index
        else:
            days_ahead = 7 - current_day_index + target_day_index
        
        # Parse target time safely
        try:
            hour, minute = map(int, target_time.split(':'))
        except (ValueError, AttributeError):
            return "Invalid time format"
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return "Invalid time"
        
        # Create target datetime
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        target += timedelta(days=days_ahead)
        
        # If it's today and time has passed, add 7 days
        if days_ahead == 0 and target <= now:
            target += timedelta(days=7)
            days_ahead = 7
        
        # Calculate difference
        diff = target - now
        total_minutes = int(diff.total_seconds() / 60)
        
        if total_minutes < 0:
            return "Time has passed"
        
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        if days_ahead == 0:
            if hours == 0:
                if minutes <= 1:
                    return f"in {minutes} minute" if minutes == 1 else "now"
                else:
                    return f"in {minutes} minutes"
            elif hours == 1:
                if minutes == 0:
                    return "in 1 hour"
                else:
                    return f"in 1 hour {minutes} minutes"
            else:
                if minutes == 0:
                    return f"in {hours} hours"
                else:
                    return f"in {hours} hours {minutes} minutes"
        elif days_ahead == 1:
            return f"tomorrow at {convert_24h_to_12h(target_time)}"
        else:
            return f"in {days_ahead} days"
            
    except Exception as e:
        return f"Error calculating time: {str(e)}"

def format_duration(seconds):
    """Format duration in seconds to readable string with error handling"""
    try:
        if not isinstance(seconds, (int, float)) or seconds < 0:
            return "0s"
        
        if seconds < 60:
            return f"{int(seconds)}s"
        else:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            
            if minutes < 60:
                return f"{minutes}m {secs}s"
            else:
                hours = minutes // 60
                minutes = minutes % 60
                return f"{hours}h {minutes}m {secs}s"
    except Exception:
        return "0s"

def safe_string_encode(text, encoding='utf-8', errors='replace'):
    """Safely encode string with fallback handling"""
    try:
        if isinstance(text, bytes):
            return text.decode(encoding, errors=errors)
        elif isinstance(text, str):
            return text
        else:
            return str(text)
    except Exception:
        return str(text) if text is not None else ""

def safe_json_loads(json_str, default=None):
    """Safely load JSON with fallback"""
    try:
        import json
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default

def safe_json_dumps(obj, default=None, ensure_ascii=False):
    """Safely dump JSON with fallback"""
    try:
        import json
        return json.dumps(obj, ensure_ascii=ensure_ascii, indent=2)
    except (TypeError, ValueError):
        return default

def create_unique_filename(base_name, extension, directory, max_attempts=1000):
    """Create a unique filename by adding numbers if file exists"""
    try:
        base_name = sanitize_filename(base_name)
        if not extension.startswith('.'):
            extension = '.' + extension
        
        # Try original name first
        filename = base_name + extension
        full_path = os.path.join(directory, filename)
        
        if not os.path.exists(full_path):
            return filename
        
        # Add numbers if file exists
        for i in range(1, max_attempts + 1):
            filename = f"{base_name}_{i}{extension}"
            full_path = os.path.join(directory, filename)
            
            if not os.path.exists(full_path):
                return filename
        
        # If all attempts failed, use timestamp
        timestamp = int(datetime.now().timestamp())
        filename = f"{base_name}_{timestamp}{extension}"
        return filename
        
    except Exception:
        # Ultimate fallback
        timestamp = int(datetime.now().timestamp())
        return f"file_{timestamp}.mp4"

def safe_remove_file(file_path, max_attempts=3):
    """Safely remove a file with retries"""
    if not file_path or not os.path.exists(file_path):
        return True
    
    for attempt in range(max_attempts):
        try:
            os.remove(file_path)
            return True
        except PermissionError:
            # File might be in use, wait and retry
            if attempt < max_attempts - 1:
                import time
                time.sleep(1)
            else:
                return False
        except Exception:
            return False
    
    return False

def safe_makedirs(directory_path, exist_ok=True):
    """Safely create directories with Unicode handling"""
    try:
        if not directory_path:
            return False
        
        os.makedirs(directory_path, exist_ok=exist_ok)
        return True
    except Exception:
        return False

def is_valid_file_path(file_path):
    """Check if a file path is valid and accessible"""
    try:
        if not file_path or not isinstance(file_path, str):
            return False
        
        # Check if path exists
        if not os.path.exists(file_path):
            return False
        
        # Check if it's a file (not directory)
        if not os.path.isfile(file_path):
            return False
        
        # Check if file has size > 0
        if os.path.getsize(file_path) == 0:
            return False
        
        # Check if file is readable
        if not os.access(file_path, os.R_OK):
            return False
        
        return True
    except Exception:
        return False

def get_safe_temp_dir():
    """Get a safe temporary directory for file operations"""
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        
        # Ensure temp directory exists and is writable
        if os.path.exists(temp_dir) and os.access(temp_dir, os.W_OK):
            return temp_dir
        
        # Fallback to current directory
        current_dir = os.getcwd()
        if os.access(current_dir, os.W_OK):
            return current_dir
        
        # Last resort - user home directory
        home_dir = os.path.expanduser("~")
        if os.access(home_dir, os.W_OK):
            return home_dir
        
        return "."  # Current directory as last resort
        
    except Exception:
        return "."

# Initialize safe file operations on import
safe_file_operations()