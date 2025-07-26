import os
from datetime import datetime

# Application Info
APP_NAME = "Twitch Clip Downloader"
APP_VERSION = "2.0"

# Directories
YOUTUBE_CREDENTIALS_DIR = "youtube_credentials"
AUTOMATION_FILE = "automation_schedules.json"

# Create directories if they don't exist
os.makedirs(YOUTUBE_CREDENTIALS_DIR, exist_ok=True)

# Default Twitch Credentials
DEFAULT_CLIENT_ID = "k85f4co8x6ce9d3whctoy75axh6k6u"
DEFAULT_CLIENT_SECRET = "o06lcyzb5sc7k5swzyfo1jrc32k2u0"

# Current date for logging
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")

# Excel settings
EXCEL_CLEANUP_DAYS = 30

# Automation settings
AUTOMATION_CHECK_INTERVAL = 10  # seconds
AUTOMATION_RETRY_DELAY = 60  # seconds
AUTOMATION_MAX_RETRIES = 5

# Video processing settings
DEFAULT_FONT_SIZE_DIVISOR = 20
STROKE_WIDTH_DIVISOR = 18

# API timeouts
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60

# Colors for Karaoke style captions
KARAOKE_COLORS = [
    '#FFFF00',  # Yellow
    '#00FF00',  # Bright Green
    '#FFFFFF',  # White
]

# YouTube settings
YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]
YOUTUBE_CATEGORY_GAMING = '20'

# Caption style descriptions
CAPTION_DESCRIPTIONS = {
    "modern": "TikTok style: White text with black outline, word-by-word animation",
    "classic": "YouTube style: White text with semi-transparent background",
    "bold": "Bold & Big: Large yellow Impact font for maximum visibility",
    "gadzhi": "Iman Gadzhi style: Gold/yellow text, luxury feel, lower third",
    "hormozi": "Alex Hormozi style: Huge white text, center screen, high impact"
}

# Language options - exactly like Twitch uses
LANGUAGES = [
    ("All Languages", "all"),
    ("English", "en"),
    ("Spanish", "es"),
    ("Portuguese", "pt"),
    ("French", "fr"),
    ("German", "de"),
    ("Italian", "it"),
    ("Russian", "ru"),
    ("Korean", "ko"),
    ("Japanese", "ja"),
    ("Chinese", "zh"),
    ("Polish", "pl"),
    ("Turkish", "tr"),
    ("Dutch", "nl"),
    ("Swedish", "sv"),
    ("Norwegian", "no"),
    ("Danish", "da"),
    ("Finnish", "fi"),
    ("Czech", "cs"),
    ("Hungarian", "hu"),
    ("Romanian", "ro"),
    ("Bulgarian", "bg"),
    ("Ukrainian", "uk"),
    ("Arabic", "ar"),
    ("Hebrew", "he"),
    ("Thai", "th"),
    ("Vietnamese", "vi"),
    ("Indonesian", "id"),
    ("Malaysian", "ms"),
    ("Hindi", "hi"),
    ("Unknown/Not Set", ""),  # For broadcasters who didn't set language
    ("Other Languages", "other")  # Catch-all for other languages
]

# Duration options
DURATION_OPTIONS = [
    ("All Durations", "all"),
    ("Short (0-15 seconds)", "0-15"),
    ("Medium (15-30 seconds)", "15-30"),
    ("Long (30-60 seconds)", "30-60"),
    ("Extra Long (60+ seconds)", "60+"),
    ("Custom Range", "custom")
]

# Caption styles
CAPTION_STYLES = [
    ("🎬 TikTok Style", "modern"),
    ("📺 Classic YouTube", "classic"),
    ("💪 Bold & Big", "bold"),
    ("💎 Iman Gadzhi Style", "gadzhi"),
    ("🔥 Alex Hormozi Style", "hormozi")
]

# Animation styles
ANIMATION_STYLES = ["pop", "fade", "slide", "zoom", "typewriter", "bounce", "Karaoke Style"]

# Privacy options
PRIVACY_OPTIONS = ["private", "unlisted", "public"]