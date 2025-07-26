import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import re
import json
import shutil
import threading
import time
import uuid
import winsound
import subprocess
import sys
from datetime import datetime

from config import *
from ui.widgets import ScrollableFrame
from ui.settings_window import SettingsWindow
from ui.youtube_upload_window import YouTubeUploadWindow
from ui.automation_ui import AutomationUI
from core.twitch_api import TwitchAPI
from core.downloader import Downloader
from core.video_processor import VideoProcessor
from core.excel_handler import ExcelHandler
from core.youtube_handler import YouTubeHandler
from core.gemini_handler import GeminiHandler
from core.automation import AutomationHandler
from utils.helpers import check_internet_connection, sanitize_filename

class TwitchClipDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title(f"🎮 {APP_NAME} v{APP_VERSION}")
        self.root.geometry("750x1400")
        
        # Initialize core components
        self.twitch_api = TwitchAPI(DEFAULT_CLIENT_ID, DEFAULT_CLIENT_SECRET)
        self.downloader = Downloader()
        self.video_processor = VideoProcessor()
        self.excel_handler = ExcelHandler()
        self.youtube_handler = YouTubeHandler()
        self.gemini_handler = GeminiHandler()
        
        # NEW: Initialize automation with task processor callback
        self.automation_handler = AutomationHandler(self.log_automation, self.show_automation_notification)
        self.automation_handler.process_single_task = self.process_automation_task  # Set callback
        
        self.automation_ui = AutomationUI(self)
        
        # UI Variables
        self.save_folder = ""
        self.downloaded_videos = []
        self.current_game_name = ""
        self.format_var = tk.StringVar(value="landscape")
        self.captions_var = tk.BooleanVar(value=True)
        self.caption_style_var = tk.StringVar(value="modern")
        self.caption_animation_var = tk.StringVar(value="pop")
        self.caption_position_var = tk.StringVar(value="center")
        self.language_var = tk.StringVar(value="all")
        self.duration_var = tk.StringVar(value="all")
        self.portrait_blur_mode_var = tk.StringVar(value="standard")
        self.portrait_blur_top_var = tk.IntVar(value=10)
        self.portrait_blur_bottom_var = tk.IntVar(value=10)
        self.use_excel_var = tk.BooleanVar(value=False)
        self.automation_enabled = tk.BooleanVar(value=False)
        
        # Download control
        self.stop_download = False
        self.download_thread = None
        
        # NEW: Sequential automation tracking
        self.automation_stats = {
            'total_triggered': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'last_success': None,
            'last_error': None
        }
        
        # Global clip tracking to prevent duplicate uploads across channels
        self.recently_used_clips = {}  # {clip_id: timestamp}
        self.clip_usage_lock = threading.Lock()  # Thread-safe access to recently_used_clips
        
        # Build UI
        self.setup_ui()
        
        # Load saved data
        self.load_saved_credentials()
        self.check_requirements()
        
        # Authenticate with Twitch
        success, message = self.twitch_api.authenticate()
        if success:
            self.log(f"✅ {message}")
        else:
            self.log(f"❌ {message}")
        
        # Load YouTube channels
        self.youtube_channels = self.youtube_handler.load_channels()
        self.refresh_youtube_channels()
        
        # Load automation schedules
        self.automation_handler.load_schedules(self.youtube_channels)
        self.refresh_automation_display()
        
        # Initialize Gemini if key exists
        if self.gemini_handler.api_key:
            self.gemini_handler.initialize(self.gemini_handler.api_key, self.log)
        
        # Start automation scheduler
        self.automation_handler.start_scheduler()
        self.log("🤖 Automation scheduler started (sequential processing)")
        
        # Start status monitoring
        self.monitor_automation_status()
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def mark_clip_as_used(self, clip_id, channel_name):
        """Mark a clip as recently used by a channel"""
        with self.clip_usage_lock:
            current_time = time.time()
            self.recently_used_clips[clip_id] = {
                'timestamp': current_time,
                'channel': channel_name
            }
            
            # Clean up old entries (older than 24 hours)
            cutoff_time = current_time - (24 * 60 * 60)  # 24 hours ago
            old_clips = [cid for cid, info in self.recently_used_clips.items() 
                        if info['timestamp'] < cutoff_time]
            for old_clip in old_clips:
                del self.recently_used_clips[old_clip]

    def is_clip_recently_used(self, clip_id):
        """Check if a clip was used recently (within last 6 hours)"""
        with self.clip_usage_lock:
            if clip_id not in self.recently_used_clips:
                return False
            
            current_time = time.time()
            clip_time = self.recently_used_clips[clip_id]['timestamp']
            
            # Consider clip "recently used" if used within last 6 hours
            return (current_time - clip_time) < (6 * 60 * 60)

    def select_unique_clip(self, clips, channel_name, format_type):
        """Select a unique clip that hasn't been used recently"""
        import random
        import hashlib
        
        available_clips = []
        
        # Filter out recently used clips
        for clip in clips:
            clip_id = clip['id']
            if not self.is_clip_recently_used(clip_id):
                available_clips.append(clip)
        
        if not available_clips:
            self.log_automation(f"⚠️ All clips recently used for {channel_name}, using random selection")
            available_clips = clips  # Fall back to all clips
        
        if not available_clips:
            return None
        
        # Use channel name and format to create deterministic but varied selection
        # This ensures different channels get different clips at the same time
        seed_string = f"{channel_name}_{format_type}_{int(time.time() / 300)}"  # Changes every 5 minutes
        seed_hash = int(hashlib.md5(seed_string.encode()).hexdigest()[:8], 16)
        
        # Use the hash to select from available clips
        selected_index = seed_hash % len(available_clips)
        selected_clip = available_clips[selected_index]
        
        self.log_automation(f"🎯 Selected clip {selected_index + 1}/{len(available_clips)} for {channel_name}: {selected_clip['title'][:50]}...")
        
        return selected_clip
    
    def on_closing(self):
        """Handle window closing"""
        self.stop_download = True
        self.automation_handler.stop_flag = True
        self.automation_handler.stop_scheduler()
        
        # Wait for threads to finish
        if self.download_thread and self.download_thread.is_alive():
            self.download_thread.join(timeout=2)
        
        # Close Excel
        self.excel_handler.close()
        
        self.root.destroy()
    
    def load_saved_credentials(self):
        """Load saved credentials from files"""
        try:
            # Load Twitch credentials
            twitch_file = os.path.join(YOUTUBE_CREDENTIALS_DIR, "twitch_credentials.json")
            if os.path.exists(twitch_file):
                try:
                    with open(twitch_file, 'r', encoding='utf-8') as f:
                        creds = json.load(f)
                        self.twitch_api.client_id = creds.get('client_id', DEFAULT_CLIENT_ID)
                        self.twitch_api.client_secret = creds.get('client_secret', DEFAULT_CLIENT_SECRET)
                        self.log("✅ Loaded saved Twitch credentials")
                except Exception as e:
                    self.log(f"⚠️ Error loading Twitch credentials: {str(e)}")
            
            # Load Gemini key
            gemini_file = os.path.join(YOUTUBE_CREDENTIALS_DIR, "gemini_key.json")
            if os.path.exists(gemini_file):
                try:
                    with open(gemini_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.gemini_handler.api_key = data.get('api_key')
                        if self.gemini_handler.api_key:
                            self.log("✅ Loaded saved Gemini API key")
                except Exception as e:
                    self.log(f"⚠️ Error loading Gemini key: {str(e)}")
        except Exception as e:
            self.log(f"⚠️ Error in load_saved_credentials: {str(e)}")
    
    def setup_ui(self):
        """Build the main UI"""
        # Create main scrollable frame
        self.main_frame = ScrollableFrame(self.root)
        self.main_frame.pack(fill="both", expand=True)
        
        # All UI elements go inside scrollable_frame
        parent = self.main_frame.scrollable_frame
        
        # Title and Settings button at the top
        title_frame = tk.Frame(parent)
        title_frame.pack(pady=10)
        
        title = tk.Label(title_frame, text=f"🎮 {APP_NAME} 🎮", 
                        font=("Arial", 20, "bold"))
        title.pack(side="left", padx=20)
        
        # Settings button
        settings_btn = tk.Button(title_frame, text="⚙️ Settings", 
                               command=self.open_settings,
                               font=("Arial", 10), bg="lightgray")
        settings_btn.pack(side="right", padx=20)
        
        # Game URL input
        tk.Label(parent, text="Paste Twitch Game Category URL:").pack()
        self.url_entry = tk.Entry(parent, width=70)
        self.url_entry.pack(pady=5)
        self.url_entry.insert(0, "https://www.twitch.tv/directory/category/fortnite")
        
        # Views Range Filter
        views_frame = tk.LabelFrame(parent, text="👁️ Views Range Filter", 
                                  font=("Arial", 11, "bold"), pady=5)
        views_frame.pack(pady=10, padx=20, fill="x")
        
        views_inner = tk.Frame(views_frame)
        views_inner.pack()
        
        tk.Label(views_inner, text="Min Views:").pack(side=tk.LEFT, padx=5)
        self.min_views_entry = tk.Entry(views_inner, width=10)
        self.min_views_entry.pack(side=tk.LEFT, padx=5)
        self.min_views_entry.insert(0, "100")
        
        tk.Label(views_inner, text="Max Views:").pack(side=tk.LEFT, padx=5)
        self.max_views_entry = tk.Entry(views_inner, width=10)
        self.max_views_entry.pack(side=tk.LEFT, padx=5)
        self.max_views_entry.insert(0, "5000")
        
        tk.Label(views_inner, text="(Leave Max empty for no limit)", 
                font=("Arial", 8), fg="gray").pack(side=tk.LEFT, padx=10)
        
        # Duration Filter
        duration_frame = tk.LabelFrame(parent, text="⏱️ Clip Duration Filter", 
                                     font=("Arial", 11, "bold"), pady=5)
        duration_frame.pack(pady=10, padx=20, fill="x")
        
        # Create duration radio buttons
        duration_inner = tk.Frame(duration_frame)
        duration_inner.pack()
        
        # Radio buttons for duration
        radio_frame = tk.Frame(duration_inner)
        radio_frame.pack()
        
        # Create radio buttons in two rows
        row1 = tk.Frame(radio_frame)
        row1.pack()
        row2 = tk.Frame(radio_frame)
        row2.pack()
        
        for i, (text, value) in enumerate(DURATION_OPTIONS):
            frame = row1 if i < 3 else row2
            rb = tk.Radiobutton(frame, text=text, variable=self.duration_var, 
                              value=value, command=self.on_duration_change)
            rb.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Custom duration inputs
        self.custom_duration_frame = tk.Frame(duration_frame)
        self.custom_duration_frame.pack(pady=5)
        
        tk.Label(self.custom_duration_frame, text="Custom range:").pack(side=tk.LEFT, padx=5)
        
        self.min_duration_entry = tk.Entry(self.custom_duration_frame, width=5)
        self.min_duration_entry.pack(side=tk.LEFT, padx=2)
        self.min_duration_entry.insert(0, "10")
        
        tk.Label(self.custom_duration_frame, text="to").pack(side=tk.LEFT, padx=2)
        
        self.max_duration_entry = tk.Entry(self.custom_duration_frame, width=5)
        self.max_duration_entry.pack(side=tk.LEFT, padx=2)
        self.max_duration_entry.insert(0, "30")
        
        tk.Label(self.custom_duration_frame, text="seconds").pack(side=tk.LEFT, padx=2)
        
        # Initially hide custom duration inputs
        self.custom_duration_frame.pack_forget()
        
        # Language Filter - Improved with Twitch API method
        language_frame = tk.LabelFrame(parent, text="🌍 Language Filter (Uses Twitch Broadcaster Settings)", 
                                     font=("Arial", 11, "bold"), pady=5)
        language_frame.pack(pady=10, padx=20, fill="x")
        
        # Create language dropdown
        language_inner = tk.Frame(language_frame)
        language_inner.pack()
        
        tk.Label(language_inner, text="Select Language:").pack(side=tk.LEFT, padx=5)
        
        self.language_menu = ttk.Combobox(language_inner, 
                                         textvariable=self.language_var,
                                         values=[lang[0] for lang in LANGUAGES],
                                         state="readonly",
                                         width=25)
        self.language_menu.current(0)
        self.language_menu.pack(side=tk.LEFT, padx=5)
        
        # Store language codes
        self.language_codes = {lang[0]: lang[1] for lang in LANGUAGES}
        
        # Add explanation
        language_info = tk.Label(language_frame, 
                               text="ℹ️ This uses the same language detection as Twitch website:\n"
                                    "• Based on broadcaster's language setting in their Twitch profile\n"
                                    "• 'Unknown/Not Set' = streamers who didn't set a language\n"
                                    "• 'Other Languages' = languages not in the main list",
                               font=("Arial", 8), fg="blue", justify="left")
        language_info.pack(pady=5)
        
        # Days to look back
        tk.Label(parent, text="How many days back to search (e.g., 7):").pack(pady=(10,0))
        self.days_entry = tk.Entry(parent, width=20)
        self.days_entry.pack(pady=5)
        self.days_entry.insert(0, "7")
        
        # Number of clips
        tk.Label(parent, text="How many clips to download (e.g., 10):").pack()
        self.clips_count_entry = tk.Entry(parent, width=20)
        self.clips_count_entry.pack(pady=5)
        self.clips_count_entry.insert(0, "1")
        
        # Format selection
        format_frame = tk.LabelFrame(parent, text="📱 Choose Video Format", 
                                   font=("Arial", 11, "bold"), pady=5)
        format_frame.pack(pady=10, padx=20, fill="x")
        
        landscape_radio = tk.Radiobutton(format_frame, 
                                       text="🖥️ Landscape (16:9) - YouTube/Normal viewing", 
                                       variable=self.format_var, 
                                       value="landscape",
                                       command=self.on_format_change,
                                       font=("Arial", 10))
        landscape_radio.pack(anchor="w", padx=20)
        
        portrait_radio = tk.Radiobutton(format_frame, 
                                      text="📱 Portrait (9:16) - TikTok/Instagram Reels/Shorts (Blurred Background)", 
                                      variable=self.format_var, 
                                      value="portrait",
                                      command=self.on_format_change,
                                      font=("Arial", 10))
        portrait_radio.pack(anchor="w", padx=20)
        
        # Portrait Blur Settings
        self.portrait_blur_frame = tk.LabelFrame(format_frame, text="🌫️ Portrait Blur Settings", 
                                               font=("Arial", 10, "bold"), pady=5)
        
        # Blur mode selection
        blur_mode_frame = tk.Frame(self.portrait_blur_frame)
        blur_mode_frame.pack(pady=5)
        
        tk.Radiobutton(blur_mode_frame, text="Standard Blur (Full Background)", 
                      variable=self.portrait_blur_mode_var, value="standard",
                      command=self.on_blur_mode_change).pack(side=tk.LEFT, padx=10)
        
        tk.Radiobutton(blur_mode_frame, text="Custom Blur Percentage", 
                      variable=self.portrait_blur_mode_var, value="custom",
                      command=self.on_blur_mode_change).pack(side=tk.LEFT, padx=10)
        
        # Custom blur percentage controls
        self.blur_percentage_frame = tk.Frame(self.portrait_blur_frame)
        self.blur_percentage_frame.pack(pady=10)
        
        # Top blur
        top_blur_frame = tk.Frame(self.blur_percentage_frame)
        top_blur_frame.pack(pady=5)
        
        tk.Label(top_blur_frame, text="Top Blur:").pack(side=tk.LEFT, padx=5)
        self.top_blur_scale = tk.Scale(top_blur_frame, from_=0, to=30, orient=tk.HORIZONTAL,
                                     variable=self.portrait_blur_top_var, length=200,
                                     command=self.update_blur_preview)
        self.top_blur_scale.pack(side=tk.LEFT, padx=5)
        self.top_blur_label = tk.Label(top_blur_frame, text="10%", width=5)
        self.top_blur_label.pack(side=tk.LEFT)
        
        # Bottom blur
        bottom_blur_frame = tk.Frame(self.blur_percentage_frame)
        bottom_blur_frame.pack(pady=5)
        
        tk.Label(bottom_blur_frame, text="Bottom Blur:").pack(side=tk.LEFT, padx=5)
        self.bottom_blur_scale = tk.Scale(bottom_blur_frame, from_=0, to=30, orient=tk.HORIZONTAL,
                                        variable=self.portrait_blur_bottom_var, length=200,
                                        command=self.update_blur_preview)
        self.bottom_blur_scale.pack(side=tk.LEFT, padx=5)
        self.bottom_blur_label = tk.Label(bottom_blur_frame, text="10%", width=5)
        self.bottom_blur_label.pack(side=tk.LEFT)
        
        # UPDATED: Better explanation for proportional scaling
        blur_info = tk.Label(self.blur_percentage_frame, 
                           text="💡 Video will SCALE UP proportionally to fill the entire clear area\n"
                                "Example: 10% top + 10% bottom = video fills 80% middle area completely",
                           font=("Arial", 9), fg="blue", justify="center")
        blur_info.pack(pady=5)
        
        # Initially hide blur frame and percentage controls
        self.portrait_blur_frame.pack_forget()
        self.blur_percentage_frame.pack_forget()
        
        # Caption Options
        self.caption_frame = tk.LabelFrame(parent, text="💬 Caption Options (Powered by MoviePy)", 
                                         font=("Arial", 11, "bold"), pady=5)
        
        # Auto captions checkbox
        self.captions_check = tk.Checkbutton(self.caption_frame, 
                                           text="✨ Add professional animated captions",
                                           variable=self.captions_var,
                                           command=self.on_caption_toggle,
                                           font=("Arial", 10))
        self.captions_check.pack(anchor="w", padx=20, pady=5)
        
        # Caption style selection
        self.style_frame = tk.Frame(self.caption_frame)
        self.style_frame.pack(anchor="w", padx=40, pady=(0, 10))
        
        tk.Label(self.style_frame, text="Caption Style:").pack(side=tk.LEFT, padx=5)
        
        # Style options
        styles_container = tk.Frame(self.style_frame)
        styles_container.pack(side=tk.LEFT, padx=10)
        
        # Create radio buttons in two rows
        row1 = tk.Frame(styles_container)
        row1.pack()
        row2 = tk.Frame(styles_container)
        row2.pack()
        
        for i, (text, value) in enumerate(CAPTION_STYLES):
            frame = row1 if i < 3 else row2
            tk.Radiobutton(frame, text=text, variable=self.caption_style_var, 
                         value=value).pack(side=tk.LEFT, padx=5)
        
        # Caption preview description
        self.caption_desc = tk.Label(self.caption_frame, 
                                   text=CAPTION_DESCRIPTIONS.get("modern", ""),
                                   font=("Arial", 9), fg="gray")
        self.caption_desc.pack(pady=5)
        
        # Caption position selection
        position_frame = tk.Frame(self.caption_frame)
        position_frame.pack(pady=5)
        
        tk.Label(position_frame, text="Caption Position:").pack(side=tk.LEFT, padx=5)
        
        position_options = [
            ("Center", "center"),
            ("Top (Edge of blur)", "top"),
            ("Bottom (Edge of blur)", "bottom")
        ]
        
        for text, value in position_options:
            tk.Radiobutton(position_frame, text=text, variable=self.caption_position_var, 
                         value=value).pack(side=tk.LEFT, padx=10)
        
        # Animation selection
        animation_frame = tk.Frame(self.caption_frame)
        animation_frame.pack(pady=5)
        
        tk.Label(animation_frame, text="Animation Style:").pack(side=tk.LEFT, padx=5)
        
        self.animation_menu = ttk.Combobox(animation_frame, 
                                         textvariable=self.caption_animation_var,
                                         values=ANIMATION_STYLES,
                                         state="readonly",
                                         width=20)
        self.animation_menu.current(0)
        self.animation_menu.pack(side=tk.LEFT, padx=5)
        
        # Update description when style changes
        self.caption_style_var.trace('w', self.update_caption_description)
        
        # Show/hide caption frame based on format
        if self.format_var.get() == "landscape":
            self.caption_frame.pack_forget()
        else:
            self.caption_frame.pack(pady=10, padx=20, fill="x", after=format_frame)
        
        # Excel Integration
        excel_frame = tk.LabelFrame(parent, text=f"📊 Excel Tracking (Auto-removes old data after {EXCEL_CLEANUP_DAYS} days)", 
                                   font=("Arial", 11, "bold"), pady=5)
        excel_frame.pack(pady=10, padx=20, fill="x")
        
        # Enable/Disable checkbox
        self.excel_check = tk.Checkbutton(excel_frame, 
                                         text="Enable Excel tracking to avoid re-downloading",
                                         variable=self.use_excel_var,
                                         command=self.on_excel_toggle,
                                         font=("Arial", 10))
        self.excel_check.pack(anchor="w", padx=20, pady=5)
        
        # Excel configuration
        self.excel_config_frame = tk.Frame(excel_frame)
        self.excel_config_frame.pack(fill="x", padx=20, pady=5)
        
        # Excel file selection
        excel_file_frame = tk.Frame(self.excel_config_frame)
        excel_file_frame.pack(fill="x", pady=5)
        
        tk.Button(excel_file_frame, text="📄 Select Excel File", 
                 command=self.choose_excel_file, bg="lightgray").pack(side=tk.LEFT, padx=5)
        
        self.excel_label = tk.Label(excel_file_frame, text="No Excel file selected", fg="gray")
        self.excel_label.pack(side=tk.LEFT)
        
        tk.Button(excel_file_frame, text="📝 Create New Excel", 
                 command=self.create_new_excel, bg="lightyellow").pack(side=tk.LEFT, padx=10)
        
        # Excel status
        self.excel_status = tk.Label(self.excel_config_frame, text="", fg="gray")
        self.excel_status.pack()
        
        # Info about auto-cleanup
        info_text = tk.Label(self.excel_config_frame, 
                           text=f"ℹ️ Excel file automatically removes entries older than {EXCEL_CLEANUP_DAYS} days\nwhen you start the app",
                           font=("Arial", 8), fg="blue")
        info_text.pack(pady=5)
        
        # Initially disable excel config
        self.on_excel_toggle()
        
        # YouTube Integration
        youtube_frame = tk.LabelFrame(parent, text="📺 YouTube Upload Integration", 
                                    font=("Arial", 11, "bold"), pady=5)
        youtube_frame.pack(pady=10, padx=20, fill="x")
        
        # YouTube info
        info = tk.Label(youtube_frame, 
                       text="Upload downloaded clips directly to YouTube!",
                       font=("Arial", 10))
        info.pack(pady=5)
        
        # Channels count label
        self.channels_count_label = tk.Label(youtube_frame, 
                                           text="No channels connected", 
                                           font=("Arial", 9), fg="gray")
        self.channels_count_label.pack()
        
        # Channels list
        channels_label = tk.Label(youtube_frame, text="Connected Channels:", font=("Arial", 10, "bold"))
        channels_label.pack()
        
        # Channels listbox with scrollbar
        channels_container = tk.Frame(youtube_frame)
        channels_container.pack(padx=20, pady=5)
        
        scrollbar = tk.Scrollbar(channels_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.channels_listbox = tk.Listbox(channels_container, height=3, 
                                         yscrollcommand=scrollbar.set)
        self.channels_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.config(command=self.channels_listbox.yview)
        
        # YouTube buttons
        youtube_buttons = tk.Frame(youtube_frame)
        youtube_buttons.pack(pady=5)
        
        tk.Button(youtube_buttons, text="🔧 Setup API", 
                 command=self.setup_youtube_api, bg="lightyellow").pack(side=tk.LEFT, padx=5)
        
        tk.Button(youtube_buttons, text="➕ Add Channel", 
                 command=self.add_youtube_channel, bg="lightgreen").pack(side=tk.LEFT, padx=5)
        
        tk.Button(youtube_buttons, text="➖ Remove Channel", 
                 command=self.remove_youtube_channel, bg="lightcoral").pack(side=tk.LEFT, padx=5)
        
        tk.Button(youtube_buttons, text="🔄 Refresh", 
                 command=self.refresh_youtube_channels).pack(side=tk.LEFT, padx=5)
        
        # YouTube setup guide
        guide_text = tk.Label(youtube_frame, 
                            text="Click 'Add Channel' to connect your YouTube channel",
                            font=("Arial", 8), fg="gray")
        guide_text.pack()
        
        # Automation & Scheduling Section
        automation_frame = tk.LabelFrame(parent, text="🤖 Automation & Scheduling", 
                                       font=("Arial", 11, "bold"), pady=5)
        automation_frame.pack(pady=10, padx=20, fill="x")
        
        # Enable automation checkbox
        self.automation_check = tk.Checkbutton(automation_frame, 
                                             text="Enable Automation (Auto-download and upload clips)",
                                             variable=self.automation_enabled,
                                             command=self.on_automation_toggle,
                                             font=("Arial", 10))
        self.automation_check.pack(anchor="w", padx=20, pady=5)
        
        # Automation status
        self.automation_status_label = tk.Label(automation_frame, text="", font=("Arial", 9))
        self.automation_status_label.pack()
        
        # Add automation notification label with bigger font and color
        self.automation_notification_label = tk.Label(automation_frame, 
                                                     text="", 
                                                     font=("Arial", 12, "bold"),
                                                     fg="red")
        self.automation_notification_label.pack(pady=5)
        
        # NEW: Sequential processing status
        self.sequential_status_label = tk.Label(automation_frame, 
                                               text="", 
                                               font=("Arial", 10),
                                               fg="blue")
        self.sequential_status_label.pack(pady=2)
        
        # Automation schedules container
        self.automation_schedules_frame = tk.Frame(automation_frame)
        self.automation_schedules_frame.pack(fill="x", padx=20, pady=5)
        
        # Store automation widgets
        self.automation_widgets = []
        
        # Add schedule button
        tk.Button(automation_frame, text="➕ Add Automation Schedule", 
                 command=self.add_automation_schedule,
                 bg="lightgreen", font=("Arial", 10)).pack(pady=5)
        
        # Automation log
        automation_log_label = tk.Label(automation_frame, text="Automation Log:", font=("Arial", 9, "bold"))
        automation_log_label.pack()
        
        # Note about requirements
        note_label = tk.Label(automation_frame, 
                            text="Note: Automation now uses SEQUENTIAL processing - one video at a time!",
                            font=("Arial", 8), fg="blue")
        note_label.pack(pady=2)
        
        automation_log_frame = tk.Frame(automation_frame)
        automation_log_frame.pack(fill="x", padx=20, pady=5)
        
        scrollbar = tk.Scrollbar(automation_log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.automation_log = tk.Text(automation_log_frame, height=5, width=70, 
                                    yscrollcommand=scrollbar.set, wrap=tk.WORD)
        self.automation_log.pack(side=tk.LEFT, fill="both", expand=True)
        scrollbar.config(command=self.automation_log.yview)
        
        # Folder selection
        folder_frame = tk.Frame(parent)
        folder_frame.pack(pady=10)
        
        tk.Button(folder_frame, text="📁 Choose Save Folder", 
                 command=self.choose_folder, bg="lightblue").pack(side=tk.LEFT, padx=5)
        
        self.folder_label = tk.Label(folder_frame, text="No folder selected")
        self.folder_label.pack(side=tk.LEFT)
        
        # Download and Stop buttons
        button_frame = tk.Frame(parent)
        button_frame.pack(pady=15)
        
        self.download_btn = tk.Button(button_frame, text="🚀 Download Clips!", 
                                     command=self.start_download,
                                     bg="green", fg="white", font=("Arial", 14),
                                     width=15, height=2)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(button_frame, text="🛑 Stop", 
                                 command=self.stop_download_process,
                                 bg="red", fg="white", font=("Arial", 14),
                                 width=10, height=2, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(parent, length=400, mode='determinate')
        self.progress.pack(pady=5)
        
        # Status text
        self.status_label = tk.Label(parent, text="Ready to download!", fg="green")
        self.status_label.pack()
        
        # Log area
        tk.Label(parent, text="Download Log:").pack()
        log_frame = tk.Frame(parent)
        log_frame.pack(pady=5, padx=20, fill="both", expand=True)
        
        # Add scrollbar to log
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(log_frame, height=10, width=70, yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill="both", expand=True)
        
        scrollbar.config(command=self.log_text.yview)
        
        # Tools status
        self.tools_frame = tk.Frame(parent)
        self.tools_frame.pack(pady=5)
        
        self.streamlink_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.streamlink_label.pack(side=tk.LEFT, padx=10)
        
        self.ffmpeg_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.ffmpeg_label.pack(side=tk.LEFT, padx=10)
        
        self.whisper_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.whisper_label.pack(side=tk.LEFT, padx=10)
        
        self.moviepy_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.moviepy_label.pack(side=tk.LEFT, padx=10)
        
        self.openpyxl_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.openpyxl_label.pack(side=tk.LEFT, padx=10)
        
        self.youtube_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.youtube_label.pack(side=tk.LEFT, padx=10)
        
        self.gemini_label = tk.Label(self.tools_frame, text="", fg="blue")
        self.gemini_label.pack(side=tk.LEFT, padx=10)
    
    def open_settings(self):
        """Open settings window"""
        try:
            SettingsWindow(self)
        except Exception as e:
            self.log(f"❌ Error opening settings: {str(e)}")
            messagebox.showerror("Error", f"Failed to open settings:\n{str(e)}")
    
    def update_blur_preview(self, value):
        """Update blur percentage labels"""
        self.top_blur_label.config(text=f"{self.portrait_blur_top_var.get()}%")
        self.bottom_blur_label.config(text=f"{self.portrait_blur_bottom_var.get()}%")
    
    def on_blur_mode_change(self):
        """Show/hide blur percentage controls based on mode"""
        if self.portrait_blur_mode_var.get() == "custom":
            self.blur_percentage_frame.pack(pady=10)
        else:
            self.blur_percentage_frame.pack_forget()
    
    def on_automation_toggle(self):
        """Handle automation enable/disable"""
        self.automation_handler.enabled = self.automation_enabled.get()
        if self.automation_enabled.get():
            self.automation_status_label.config(text="Automation is running (Sequential Processing)", fg="green")
            self.log_automation("✅ Automation enabled - sequential processing")
        else:
            self.automation_status_label.config(text="Automation is stopped", fg="red")
            self.log_automation("🛑 Automation disabled")
            # Clear notification when disabled
            self.automation_notification_label.config(text="")
            self.sequential_status_label.config(text="")
    
    def show_automation_notification(self, message, color="red"):
        """Show a prominent notification for automation events"""
        if hasattr(self, 'automation_notification_label'):
            self.automation_notification_label.config(text=message, fg=color)
        
        # Also log to automation log
        self.log_automation(f"🔔 {message}")
        
        # Play Windows notification sound for important events
        try:
            if "ERROR" in message or "FAILED" in message:
                winsound.PlaySound("SystemHand", winsound.SND_ALIAS)
            elif "SUCCESS" in message:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
            else:
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
        except:
            pass  # If sound fails, continue anyway
        
        # Clear the notification after 30 seconds
        if hasattr(self, 'automation_notification_label'):
            self.root.after(30000, lambda: self.automation_notification_label.config(text=""))
    
    def log_automation(self, message):
        """Log automation messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        
        if hasattr(self, 'automation_log'):
            self.automation_log.insert(tk.END, f"{full_message}\n")
            self.automation_log.see(tk.END)
        
        # Also log to main log for debugging
        self.log(f"AUTO: {message}")
        
        self.root.update_idletasks()
    
    def monitor_automation_status(self):
        """NEW: Monitor automation status and update UI"""
        try:
            if hasattr(self, 'automation_handler') and self.automation_enabled.get():
                status_info = self.automation_handler.get_status_info()
                
                # Update sequential status
                queue_size = status_info.get('queue_size', 0)
                current_task = status_info.get('current_task')
                total_processed = status_info.get('total_processed', 0)
                
                if current_task:
                    # Show what's currently processing
                    task_info = f"Processing: {current_task['schedule'].channel_name} ({current_task['format_type']})"
                    if queue_size > 0:
                        task_info += f" | Queue: {queue_size} pending"
                    self.sequential_status_label.config(text=task_info, fg="blue")
                elif queue_size > 0:
                    # Show queue status
                    self.sequential_status_label.config(text=f"⏳ Queue: {queue_size} tasks waiting", fg="orange")
                elif total_processed > 0:
                    # Show completion status
                    successful = status_info.get('successful_tasks', 0)
                    failed = status_info.get('failed_tasks', 0)
                    self.sequential_status_label.config(text=f"✅ Processed: {total_processed} ({successful} success, {failed} failed)", fg="green")
                else:
                    # Show idle status
                    self.sequential_status_label.config(text="🔄 Sequential worker ready", fg="gray")
            else:
                self.sequential_status_label.config(text="", fg="gray")
        
        except Exception as e:
            # Don't spam errors, just log once
            pass
        
        # Schedule next update
        self.root.after(2000, self.monitor_automation_status)  # Check every 2 seconds
    
    def process_automation_task(self, task_data):
        """NEW: Process a single automation task (called by sequential worker)"""
        schedule = task_data['schedule']
        format_type = task_data['format_type']
        unique_id = task_data.get('unique_id', str(uuid.uuid4()))
        thread_name = f"SeqUpload-{schedule.channel_name.replace(' ', '_')}-{format_type}"
        
        # Create HIGHLY unique temporary folder for this task
        timestamp_ms = int(time.time() * 1000)
        temp_folder_name = f"seq_automation_{schedule.channel_name.replace(' ', '_')}_{format_type}_{timestamp_ms}_{unique_id[:8]}"
        temp_folder = os.path.join(self.save_folder, temp_folder_name)
        
        try:
            # Register temp folder for cleanup
            self.automation_handler.register_temp_folder(temp_folder)
            
            self.log_automation(f"🚀 [{thread_name}] Starting sequential task for {schedule.channel_name}")
            
            # Validate save folder
            if not self.save_folder or not os.path.exists(self.save_folder):
                error_msg = "Save folder not selected or doesn't exist"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"❌ FOLDER ERROR: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                return
            
            # Create unique temporary folder
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    os.makedirs(temp_folder, exist_ok=True)
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(0.5 + attempt * 0.2)
                        temp_folder = os.path.join(self.save_folder, f"seq_automation_{schedule.channel_name.replace(' ', '_')}_{format_type}_{timestamp_ms}_{unique_id[:8]}_{attempt}")
                    else:
                        self.log_automation(f"❌ [{thread_name}] Failed to create temp folder after {max_retries} attempts: {str(e)}")
                        self.show_automation_notification(f"❌ TEMP FOLDER ERROR: {schedule.channel_name}", "red")
                        return
            
            # Check internet connection
            if not check_internet_connection():
                error_msg = "No internet connection"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"⚠️ NO INTERNET: {schedule.channel_name}", "orange")
                self.automation_handler.failed_tasks += 1
                return
            
            # Validate game settings
            if not schedule.game_id or not schedule.game_name:
                # Try to get game info
                game_id, game_name = self.twitch_api.get_game_id(schedule.game_category)
                if not game_id:
                    error_msg = f"Invalid game URL: {schedule.game_category}"
                    self.log_automation(f"❌ [{thread_name}] {error_msg}")
                    self.show_automation_notification(f"❌ INVALID GAME: {schedule.channel_name}", "red")
                    self.automation_handler.failed_tasks += 1
                    return
                
                # Update schedule with valid game info
                schedule.game_id = game_id
                schedule.game_name = game_name
                self.automation_handler.save_schedules()
            
            # Show processing notification
            self.show_automation_notification(
                f"🔄 PROCESSING: {schedule.channel_name} - {format_type} video",
                "blue"
            )
            
            # Get today's date and check upload limits
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str not in schedule.daily_upload_count:
                schedule.daily_upload_count[today_str] = {'landscape': 0, 'portrait': 0}
            
            counts = schedule.daily_upload_count[today_str]
            
            # Check if we've already uploaded enough today
            if format_type == 'landscape' and counts.get('landscape', 0) >= schedule.landscape_videos_per_day:
                self.log_automation(f"ℹ️ [{thread_name}] Daily landscape limit reached for {schedule.channel_name}")
                return
            if format_type == 'portrait' and counts.get('portrait', 0) >= schedule.portrait_videos_per_day:
                self.log_automation(f"ℹ️ [{thread_name}] Daily portrait limit reached for {schedule.channel_name}")
                return
            
            self.log_automation(f"🔍 [{thread_name}] Searching for {format_type} clips...")
            
            # Get duration range
            if schedule.duration_range == "custom":
                min_duration = schedule.custom_min_duration
                max_duration = schedule.custom_max_duration
            elif schedule.duration_range == "all":
                min_duration = None
                max_duration = None
            else:
                parts = schedule.duration_range.split('-')
                min_duration = int(parts[0])
                max_duration = int(parts[1]) if len(parts) > 1 else float('inf')
            
            # Get days back setting
            days_back = getattr(schedule, 'days_back', 7)
            
            # Get language filter setting
            language_filter = getattr(schedule, 'language_filter', 'all')
            
            # Find clips with language filter
            clips, _ = self.twitch_api.get_clips(
                schedule.game_id,
                schedule.game_name,
                schedule.min_views,
                schedule.max_views,
                days_back,
                5,  # Get 5 clips to have options
                language_filter,  # Use schedule's language filter
                min_duration,
                max_duration,
                check_downloaded_func=self.excel_handler.check_if_downloaded if self.use_excel_var.get() else None,
                log_func=lambda msg: self.log_automation(f"[{thread_name}] {msg}"),
                stop_check_func=lambda: False
            )
            
            if not clips:
                error_msg = f"No clips found matching criteria for {schedule.game_name}"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"❌ NO CLIPS: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                return
            
            # Select clip using smart selection to avoid duplicates
            clip = self.select_unique_clip(clips, schedule.channel_name, format_type)
            if not clip:
                error_msg = f"No suitable clips available for {schedule.channel_name}"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"❌ NO SUITABLE CLIPS: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                return

            # Mark this clip as used BEFORE downloading to prevent other threads from using it
            self.mark_clip_as_used(clip['id'], schedule.channel_name)
            
            # Create HIGHLY unique filename
            clip_title = sanitize_filename(clip['title'])
            timestamp = datetime.now().strftime("%H%M%S_%f")
            process_id = os.getpid()
            channel_safe = schedule.channel_name.replace(' ', '_').replace('-', '_')
            
            if format_type == "portrait":
                filename = f"seq_{channel_safe}_{timestamp}_{process_id}_{clip_title[:20]}_{clip['id']}_portrait.mp4"
            else:
                filename = f"seq_{channel_safe}_{timestamp}_{process_id}_{clip_title[:20]}_{clip['id']}.mp4"
            
            save_path = os.path.join(temp_folder, filename)
            temp_path = os.path.join(temp_folder, f"temp_{unique_id[:8]}_{timestamp}_{clip['id']}.mp4")
            
            # Download the clip with retry logic
            self.log_automation(f"⬇️ [{thread_name}] Downloading: {clip['title']}")
            
            download_success = False
            for download_attempt in range(3):
                try:
                    if self.downloader.download_clip(
                        clip, 
                        temp_path, 
                        lambda msg: self.log_automation(f"[{thread_name}] {msg}"),
                        lambda: False
                    ):
                        download_success = True
                        break
                    else:
                        if download_attempt < 2:
                            self.log_automation(f"⚠️ [{thread_name}] Download attempt {download_attempt + 1} failed, retrying...")
                            time.sleep(2 + download_attempt)
                        else:
                            self.log_automation(f"❌ [{thread_name}] All download attempts failed")
                except Exception as e:
                    self.log_automation(f"❌ [{thread_name}] Download error: {str(e)}")
                    if download_attempt < 2:
                        time.sleep(2 + download_attempt)
            
            if not download_success:
                error_msg = f"Failed to download clip: {clip['title']}"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"❌ DOWNLOAD FAILED: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                return
            
            # Wait for file to be fully written
            time.sleep(1.0)
            
            # Convert if needed with improved error handling
            conversion_success = False
            if format_type == "portrait":
                # Setup caption settings from schedule
                caption_settings = {
                    'style': schedule.portrait_caption_style,
                    'animation': schedule.portrait_caption_animation,
                    'position': schedule.portrait_caption_position
                }
                
                # Get blur settings
                blur_top = getattr(schedule, 'portrait_blur_top', 0)
                blur_bottom = getattr(schedule, 'portrait_blur_bottom', 0)
                blur_mode = 'custom' if (blur_top > 0 or blur_bottom > 0) else 'standard'
                
                self.log_automation(f"🎨 [{thread_name}] Converting to portrait format (9:16 aspect ratio)...")
                if blur_mode == 'custom':
                    self.log_automation(f"   Using custom blur: {blur_top}% top, {blur_bottom}% bottom")
                    self.log_automation(f"   Video will scale UP to fill {100 - blur_top - blur_bottom}% clear area")
                
                for convert_attempt in range(3):
                    try:
                        # Use the safe conversion method
                        conversion_success = self.safe_convert_to_portrait(
                            temp_path, save_path, 
                            add_captions=schedule.portrait_captions_enabled,
                            blur_mode=blur_mode,
                            blur_top=blur_top,
                            blur_bottom=blur_bottom,
                            caption_settings=caption_settings,
                            log_func=lambda msg: self.log_automation(f"[{thread_name}] {msg}")
                        )
                        
                        if conversion_success:
                            self.log_automation(f"✅ [{thread_name}] Successfully converted to 9:16 portrait format")
                            break
                        else:
                            if convert_attempt < 2:
                                self.log_automation(f"⚠️ [{thread_name}] Conversion attempt {convert_attempt + 1} failed, retrying...")
                                time.sleep(2 + convert_attempt)
                    except Exception as e:
                        self.log_automation(f"❌ [{thread_name}] Conversion error: {str(e)}")
                        if convert_attempt < 2:
                            time.sleep(2 + convert_attempt)
                
                if conversion_success:
                    # Clean up temp file
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except:
                        pass
                else:
                    error_msg = "Failed to convert to portrait format"
                    self.log_automation(f"❌ [{thread_name}] {error_msg}")
                    self.show_automation_notification(f"❌ CONVERT FAILED: {schedule.channel_name}", "red")
                    self.automation_handler.failed_tasks += 1
                    return
            else:
                # Just move the file for landscape with retry logic
                for move_attempt in range(5):
                    try:
                        time.sleep(0.5 + move_attempt * 0.1)
                        shutil.move(temp_path, save_path)
                        conversion_success = True
                        self.log_automation(f"✅ [{thread_name}] Landscape video prepared")
                        break
                    except Exception as e:
                        if move_attempt < 4:
                            self.log_automation(f"⚠️ [{thread_name}] File move attempt {move_attempt + 1} failed, retrying... ({str(e)})")
                            time.sleep(1 + move_attempt * 0.2)
                        else:
                            error_msg = f"Error moving file after 5 attempts: {str(e)}"
                            self.log_automation(f"❌ [{thread_name}] {error_msg}")
                            self.show_automation_notification(f"❌ FILE MOVE ERROR: {schedule.channel_name}", "red")
                            self.automation_handler.failed_tasks += 1
                            return
            
            if not conversion_success:
                return
            
            # Verify file exists and has size > 0
            if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                self.log_automation(f"❌ [{thread_name}] Final video file is missing or empty")
                self.show_automation_notification(f"❌ FILE ERROR: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                return
            
            self.log_automation(f"✅ [{thread_name}] Downloaded: {clip['title']}")
            
            # Generate title and description with improved error handling
            title = None
            description = None
            used_gemini = False
            
            # Check if Gemini should be used
            if hasattr(schedule, 'use_gemini_titles') and schedule.use_gemini_titles and self.gemini_handler.model:
                self.log_automation(f"🤖 [{thread_name}] Attempting Gemini AI title generation...")
                
                try:
                    # Get transcript for Gemini
                    self.log_automation(f"🎤 [{thread_name}] Extracting transcript...")
                    transcript = self.video_processor.get_transcript(save_path)
                    
                    # Generate with Gemini
                    clip_index = counts.get('landscape', 0) + counts.get('portrait', 0)
                    if transcript or clip['title']:
                        content_for_gemini = transcript if transcript else f"Clip title: {clip['title']}"
                        
                        # Show progress
                        self.show_automation_notification(
                            f"🤖 GEMINI AI: Generating title for {schedule.channel_name}",
                            "blue"
                        )
                        
                        # Set timeout for automation
                        original_timeout = self.gemini_handler.timeout_seconds
                        self.gemini_handler.timeout_seconds = 45
                        
                        try:
                            title, description = self.gemini_handler.generate_youtube_content(
                                content_for_gemini, 
                                schedule.game_name, 
                                is_portrait=(format_type == "portrait"),
                                clip_index=clip_index,
                                log_func=lambda msg: self.log_automation(f"[{thread_name}] {msg}")
                            )
                            
                            if title and description:
                                used_gemini = True
                                self.log_automation(f"✅ [{thread_name}] Gemini generated title successfully")
                            else:
                                self.log_automation(f"⚠️ [{thread_name}] Gemini returned empty response, using fallback")
                                
                        finally:
                            self.gemini_handler.timeout_seconds = original_timeout
                        
                    else:
                        self.log_automation(f"⚠️ [{thread_name}] No transcript or title available for Gemini")
                        
                except Exception as gemini_error:
                    self.log_automation(f"❌ [{thread_name}] Gemini error: {str(gemini_error)}")
                    self.show_automation_notification(
                        f"⚠️ GEMINI FAILED: Using default title for {schedule.channel_name}",
                        "orange"
                    )
            
            # Fallback to default if Gemini failed or not enabled
            if not title or not description:
                if not used_gemini:
                    self.log_automation(f"📝 [{thread_name}] Using default title generation")
                
                format_tag = "#Shorts" if format_type == "portrait" else ""
                title = f"{clip['title']} - {schedule.game_name} {format_tag}".strip()[:100]
                description = f"Gaming clip from {schedule.game_name}\n\n#gaming #{schedule.game_name.replace(' ', '').lower()}"
                if format_type == "portrait":
                    description += " #shorts #viral #fyp"
            
            # Upload to YouTube
            self.log_automation(f"📤 [{thread_name}] Uploading to YouTube...")
            self.show_automation_notification(
                f"📤 UPLOADING: {title[:30]}... to {schedule.channel_name}",
                "blue"
            )
            
            video_id = self.youtube_handler.upload_video(
                schedule.channel_data,
                save_path,
                title,
                description,
                schedule.privacy,
                False,
                None,
                tags=['gaming', 'twitch', 'clips', schedule.game_name],
                log_func=lambda msg: self.log_automation(f"[{thread_name}] {msg}")
            )
            
            if video_id:
                # Success!
                success_msg = f"Successfully uploaded {format_type} video"
                if used_gemini:
                    success_msg += " (Gemini AI title)"
                
                self.log_automation(f"✅ [{thread_name}] {success_msg}: {title}")
                self.show_automation_notification(
                    f"✅ SUCCESS: Uploaded to {schedule.channel_name}!",
                    "green"
                )
                
                # Update counts
                if format_type == 'landscape':
                    schedule.daily_upload_count[today_str]['landscape'] += 1
                else:
                    schedule.daily_upload_count[today_str]['portrait'] += 1
                
                self.automation_handler.save_schedules()
                self.root.after(100, self.refresh_automation_display)  # Update UI safely
                
                # Update stats
                self.automation_handler.successful_tasks += 1
                self.automation_stats['successful_uploads'] += 1
                self.automation_stats['last_success'] = datetime.now().strftime("%H:%M:%S")
                
                # Add to Excel if enabled
                if self.use_excel_var.get():
                    self.excel_handler.add_clip(clip, schedule.game_name)
                
                # Reset Gemini failure counter on successful upload
                if hasattr(self.gemini_handler, 'reset_failure_counter'):
                    self.gemini_handler.reset_failure_counter()
                
            else:
                error_msg = "Failed to upload video to YouTube"
                self.log_automation(f"❌ [{thread_name}] {error_msg}")
                self.show_automation_notification(f"❌ UPLOAD FAILED: {schedule.channel_name}", "red")
                self.automation_handler.failed_tasks += 1
                self.automation_stats['failed_uploads'] += 1
                self.automation_stats['last_error'] = datetime.now().strftime("%H:%M:%S")
                    
        except Exception as e:
            error_msg = f"Critical automation error: {str(e)}"
            self.log_automation(f"❌ [{thread_name}] {error_msg}")
            self.show_automation_notification(f"❌ CRITICAL ERROR: {schedule.channel_name}", "red")
            self.automation_handler.failed_tasks += 1
            self.automation_stats['failed_uploads'] += 1
            self.automation_stats['last_error'] = datetime.now().strftime("%H:%M:%S")
            
            # Log detailed error for debugging (but safely)
            try:
                import traceback
                error_details = traceback.format_exc()
                # Only log first few lines to avoid spam
                error_lines = error_details.split('\n')[:5]
                self.log_automation(f"🔍 [{thread_name}] Error details: {' | '.join(error_lines)}")
            except:
                pass
        
        finally:
            # Clean up files and temp folder
            try:
                # Clean up the final file
                if 'save_path' in locals() and os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except:
                        pass
                
                # Clean up any remaining temp files
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                
            except Exception as cleanup_error:
                self.log_automation(f"⚠️ [{thread_name}] Cleanup error: {str(cleanup_error)}")
            
            # Unregister temp folder (this will clean it up)
            self.automation_handler.unregister_temp_folder(temp_folder)
            
            self.log_automation(f"🏁 [{thread_name}] Sequential task completed for {schedule.channel_name}")
    
    def safe_convert_to_portrait(self, input_path, output_path, add_captions=False, 
                                blur_mode="standard", blur_top=0, blur_bottom=0,
                                caption_settings=None, log_func=None):
        """NEW: Safely convert video to portrait with better Unicode/error handling - UPDATED FOR PROPORTIONAL SCALING"""
        try:
            # First try with the video processor
            success = self.video_processor.convert_to_portrait(
                input_path, output_path, add_captions, blur_mode, 
                blur_top, blur_bottom, caption_settings, log_func
            )
            
            if success:
                return True
            
            # If that fails, try a simpler FFmpeg approach with better encoding
            if log_func:
                log_func("⚠️ Conversion attempt 1 failed, retrying with safe encoding...")
            
            # Create a safe FFmpeg command that handles Unicode better
            return self.safe_ffmpeg_convert(input_path, output_path, blur_mode, blur_top, blur_bottom, log_func)
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Safe conversion error: {str(e)}")
            return False
    
    def safe_ffmpeg_convert(self, input_path, output_path, blur_mode, blur_top, blur_bottom, log_func=None):
        """NEW: Safe FFmpeg conversion with Unicode handling - UPDATED FOR PROPORTIONAL SCALING"""
        try:
            if log_func:
                log_func("🔧 Using safe FFmpeg conversion...")
            
            # Use a simple 9:16 conversion that's less likely to fail
            target_width = 1080
            target_height = 1920
            
            if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0):
                # Calculate clear area for the improved proportional scaling
                clear_height_percent = (100 - blur_top - blur_bottom) / 100.0
                clear_area_height = int(target_height * clear_height_percent)
                y_offset = int(target_height * blur_top / 100)
                
                if log_func:
                    log_func(f"   Custom blur: {blur_top}% top, {blur_bottom}% bottom")
                    log_func(f"   Video will scale UP to fill {int(clear_height_percent * 100)}% clear area")
                
                # UPDATED: Scale UP to fill the clear area completely (force_original_aspect_ratio=increase)
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{target_height},"
                    f"gblur=sigma=15[background];"
                    f"[0:v]scale={target_width}:{clear_area_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{clear_area_height}[scaled];"
                    f"[background][scaled]overlay=0:{y_offset}:shortest=1"
                )
            else:
                # Standard blur
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
                )
            
            # Build FFmpeg command with safe encoding
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-filter_complex' if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0) else '-vf', 
                filter_string,
                '-map', '0:a?' if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0) else None,
                '-c:v', 'libx264',
                '-c:a', 'aac' if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0) else 'copy',
                '-preset', 'ultrafast',  # Use fastest preset
                '-crf', '23',
                '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
                '-fflags', '+genpts',  # Generate timestamps
                '-y',
                output_path
            ]
            
            # Remove None values from cmd
            cmd = [arg for arg in cmd if arg is not None]
            
            # Execute with better error handling
            if log_func:
                log_func("   Executing safe FFmpeg command...")
            
            # Use safer subprocess execution
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'  # Force UTF-8 encoding
            
            try:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True,
                    timeout=180,  # 3 minute timeout
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    env=env,
                    encoding='utf-8',
                    errors='replace'  # Replace invalid Unicode characters
                )
                
                if result.returncode == 0:
                    if log_func:
                        log_func(f"   ✅ Safe FFmpeg conversion successful")
                    return True
                else:
                    # Log error but in a safe way
                    error_msg = result.stderr if result.stderr else "Unknown FFmpeg error"
                    # Truncate very long error messages
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                    if log_func:
                        log_func(f"   ❌ Safe FFmpeg failed: {error_msg}")
                    return False
                    
            except subprocess.TimeoutExpired:
                if log_func:
                    log_func(f"   ❌ Safe FFmpeg timeout after 3 minutes")
                return False
            except UnicodeDecodeError:
                if log_func:
                    log_func(f"   ❌ Safe FFmpeg Unicode error")
                return False
            except Exception as e:
                if log_func:
                    log_func(f"   ❌ Safe FFmpeg error: {str(e)}")
                return False
                
        except Exception as e:
            if log_func:
                log_func(f"❌ Safe FFmpeg conversion failed: {str(e)}")
            return False
    
    def add_automation_schedule(self):
        """Add a new automation schedule"""
        self.automation_ui.create_schedule_window(
            self.youtube_channels,
            self.save_folder,
            self.url_entry.get()
        )
    
    def refresh_automation_display(self):
        """Refresh the display of automation schedules"""
        # Clear existing widgets
        for widget in self.automation_widgets:
            widget.destroy()
        self.automation_widgets.clear()
        
        # Display each schedule
        for i, schedule in enumerate(self.automation_handler.schedules):
            frame = tk.LabelFrame(self.automation_schedules_frame, 
                                 text=f"Schedule {i+1}: {schedule.channel_name}",
                                 font=("Arial", 9, "bold"), padx=10, pady=5)
            frame.pack(fill="x", pady=5)
            self.automation_widgets.append(frame)
            
            # Calculate total videos
            total_videos = schedule.landscape_videos_per_day + schedule.portrait_videos_per_day
            
            # Get active days
            active_days = [day[:3] for day, config in schedule.weekly_schedule.items() 
                          if config['enabled'] and config['times']]
            
            # Get days back setting
            days_back = getattr(schedule, 'days_back', 7)
            
            # Get language display name
            language_display = "All Languages"
            if hasattr(schedule, 'language_filter') and schedule.language_filter != 'all':
                from config import LANGUAGES
                language_display = next((lang[0] for lang in LANGUAGES if lang[1] == schedule.language_filter), 
                                      schedule.language_filter)
            
            # Schedule info with days back and language
            info_text = (f"📹 {total_videos} videos/day ({schedule.landscape_videos_per_day} landscape, "
                        f"{schedule.portrait_videos_per_day} portrait)\n"
                        f"📅 Active days: {', '.join(active_days) if active_days else 'None'} | "
                        f"🔍 Search last {days_back} days\n"
                        f"👁️ Views: {schedule.min_views}-{schedule.max_views} | "
                        f"🌍 Language: {language_display}\n"
                        f"🎮 Game: {schedule.game_name} | 🔒 Privacy: {schedule.privacy}")
            
            # Add Gemini status
            if hasattr(schedule, 'use_gemini_titles') and schedule.use_gemini_titles:
                info_text += f"\n🤖 Gemini AI: Enabled ({schedule.gemini_creativity} mode)"
            
            if schedule.portrait_videos_per_day > 0 and schedule.portrait_captions_enabled:
                info_text += f"\n💬 Portrait captions: {schedule.portrait_caption_style} style"
                
                # Show blur settings if custom
                blur_top = getattr(schedule, 'portrait_blur_top', 0)
                blur_bottom = getattr(schedule, 'portrait_blur_bottom', 0)
                if blur_top > 0 or blur_bottom > 0:
                    info_text += f" | Custom Blur: {blur_top}% top, {blur_bottom}% bottom (scales to fill {100 - blur_top - blur_bottom}%)"
            
            info_label = tk.Label(frame, text=info_text, font=("Arial", 8), justify="left")
            info_label.pack(anchor="w")
            
            # Status and next upload time
            status_text = f"Status: {'Enabled' if schedule.enabled else 'Disabled'}"
            
            # Get today's upload count
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str in schedule.daily_upload_count:
                counts = schedule.daily_upload_count[today_str]
                total_uploaded = counts.get('landscape', 0) + counts.get('portrait', 0)
                status_text += f" | Today: {total_uploaded} uploaded"
            
            # Calculate next upload time
            if schedule.enabled:
                next_upload = self.automation_ui.calculate_next_upload_time(schedule)
                status_text += f" | Next: {next_upload}"
            
            status_label = tk.Label(frame, text=status_text, font=("Arial", 8), 
                                  fg="green" if schedule.enabled else "red")
            status_label.pack(anchor="w")
            
            # Buttons
            button_frame = tk.Frame(frame)
            button_frame.pack(anchor="w", pady=5)
            
            # Check if automation is running
            automation_running = self.automation_enabled.get()
            
            tk.Button(button_frame, text="Toggle", 
                     command=lambda idx=i: self.toggle_schedule(idx),
                     bg="yellow").pack(side=tk.LEFT, padx=5)
            
            # Edit button - disabled when automation is running
            edit_btn = tk.Button(button_frame, text="✏️ Edit", 
                               command=lambda idx=i: self.edit_schedule(idx),
                               bg="lightblue", fg="black",
                               state="disabled" if automation_running else "normal")
            edit_btn.pack(side=tk.LEFT, padx=5)
            
            # Duplicate button - disabled when automation is running  
            duplicate_btn = tk.Button(button_frame, text="📋 Duplicate", 
                                    command=lambda idx=i: self.duplicate_schedule(idx),
                                    bg="lightgreen", fg="black",
                                    state="disabled" if automation_running else "normal")
            duplicate_btn.pack(side=tk.LEFT, padx=5)
            
            tk.Button(button_frame, text="❌ Remove", 
                     command=lambda idx=i: self.remove_schedule(idx),
                     bg="red", fg="white").pack(side=tk.LEFT, padx=5)
    
    def toggle_schedule(self, index):
        """Toggle a schedule on/off"""
        self.automation_handler.toggle_schedule(index)
        self.refresh_automation_display()
        status = "enabled" if self.automation_handler.schedules[index].enabled else "disabled"
        self.log_automation(f"Schedule {index+1} {status}")
    
    def remove_schedule(self, index):
        """Remove an automation schedule"""
        schedule = self.automation_handler.schedules[index]
        result = messagebox.askyesno("Confirm Removal", 
                                   f"Remove schedule for {schedule.channel_name}?")
        if result:
            self.automation_handler.remove_schedule(index)
            self.refresh_automation_display()
            self.log_automation(f"❌ Removed schedule for {schedule.channel_name}")

    def edit_schedule(self, index):
        """Edit an existing automation schedule"""
        if index < 0 or index >= len(self.automation_handler.schedules):
            messagebox.showerror("Error", "Invalid schedule index!")
            return
        
        if self.automation_enabled.get():
            messagebox.showwarning("Automation Running", 
                                 "Cannot edit schedules while automation is running!\n\n"
                                 "Please disable automation first.")
            return
        
        schedule_to_edit = self.automation_handler.schedules[index]
        
        # Open schedule window in edit mode
        self.automation_ui.create_schedule_window(
            self.youtube_channels,
            self.save_folder,
            self.url_entry.get(),
            edit_mode=True,
            existing_schedule=schedule_to_edit,
            schedule_index=index
        )
    
    def duplicate_schedule(self, index):
        """Duplicate an existing automation schedule"""
        if index < 0 or index >= len(self.automation_handler.schedules):
            messagebox.showerror("Error", "Invalid schedule index!")
            return
        
        if self.automation_enabled.get():
            messagebox.showwarning("Automation Running", 
                                 "Cannot duplicate schedules while automation is running!\n\n"
                                 "Please disable automation first.")
            return
        
        original_schedule = self.automation_handler.schedules[index]
        
        # Create a copy of the schedule
        from core.automation import AutomationSchedule
        duplicate_schedule = AutomationSchedule()
        
        # Copy all settings from original
        duplicate_schedule.landscape_videos_per_day = original_schedule.landscape_videos_per_day
        duplicate_schedule.portrait_videos_per_day = original_schedule.portrait_videos_per_day
        duplicate_schedule.weekly_schedule = original_schedule.weekly_schedule.copy()
        duplicate_schedule.min_views = original_schedule.min_views
        duplicate_schedule.max_views = original_schedule.max_views
        duplicate_schedule.duration_range = original_schedule.duration_range
        duplicate_schedule.custom_min_duration = original_schedule.custom_min_duration
        duplicate_schedule.custom_max_duration = original_schedule.custom_max_duration
        duplicate_schedule.game_category = original_schedule.game_category
        duplicate_schedule.game_id = original_schedule.game_id
        duplicate_schedule.game_name = original_schedule.game_name
        duplicate_schedule.privacy = original_schedule.privacy
        duplicate_schedule.days_back = original_schedule.days_back
        duplicate_schedule.portrait_captions_enabled = original_schedule.portrait_captions_enabled
        duplicate_schedule.portrait_caption_style = original_schedule.portrait_caption_style
        duplicate_schedule.portrait_caption_animation = original_schedule.portrait_caption_animation
        duplicate_schedule.portrait_caption_position = original_schedule.portrait_caption_position
        duplicate_schedule.portrait_blur_top = getattr(original_schedule, 'portrait_blur_top', 0)
        duplicate_schedule.portrait_blur_bottom = getattr(original_schedule, 'portrait_blur_bottom', 0)
        duplicate_schedule.use_gemini_titles = getattr(original_schedule, 'use_gemini_titles', False)
        duplicate_schedule.gemini_creativity = getattr(original_schedule, 'gemini_creativity', "balanced")
        duplicate_schedule.language_filter = getattr(original_schedule, 'language_filter', "all")
        
        # Set new name (will be changed by user)
        duplicate_schedule.channel_name = f"{original_schedule.channel_name} (Copy)"
        
        # Open schedule window in duplicate mode
        self.automation_ui.create_schedule_window(
            self.youtube_channels,
            self.save_folder,
            self.url_entry.get(),
            edit_mode=False,  # It's not editing, it's creating new
            existing_schedule=duplicate_schedule,
            schedule_index=None  # No index since it's new
        )        
    
    def setup_youtube_api(self):
        """Help user set up YouTube API credentials"""
        try:
            # Create dialog to choose credential management
            choice = messagebox.askyesnocancel(
                "YouTube API Credentials Setup",
                "How would you like to manage YouTube API credentials?\n\n"
                "YES - Add new credentials (for a new Google account)\n"
                "NO - View/manage existing credentials\n"
                "CANCEL - Cancel setup"
            )
            
            if choice is True:  # Add new credentials
                self.add_new_credentials()
            elif choice is False:  # Manage existing
                self.manage_credentials()
        except Exception as e:
            self.log(f"❌ Error in setup_youtube_api: {str(e)}")
            messagebox.showerror("Error", f"Failed to open setup:\n{str(e)}")
    
    def add_new_credentials(self):
        """Add new Google Cloud credentials"""
        try:
            # Ask for a name for these credentials
            cred_name = simpledialog.askstring(
                "Credential Name",
                "Enter a name for these credentials\n(e.g., 'Personal Gmail', 'Work Account'):"
            )
            
            if not cred_name:
                return
            
            # Sanitize the name for filename
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', cred_name)
            client_secret_path = os.path.join(YOUTUBE_CREDENTIALS_DIR, f"client_secret_{safe_name}.json")
            
            if os.path.exists(client_secret_path):
                if not messagebox.askyesno("Credentials Exist", 
                                         f"Credentials for '{cred_name}' already exist.\n"
                                         "Do you want to replace them?"):
                    return
            
            # Now let them add the file
            choice = messagebox.askyesnocancel(
                "Add Credentials",
                f"Adding credentials for: {cred_name}\n\n"
                "YES - Open Google Cloud Console to create new\n"
                "NO - Browse for existing client_secret.json\n"
                "CANCEL - Cancel"
            )
            
            if choice is True:  # Open browser
                import webbrowser
                webbrowser.open("https://console.cloud.google.com/apis/credentials")
                
                instructions = (
                    f"CREATING CREDENTIALS FOR: {cred_name}\n\n"
                    "1. In Google Cloud Console:\n"
                    "   - Create new project or select existing\n"
                    "   - Enable 'YouTube Data API v3'\n\n"
                    "2. Create Credentials:\n"
                    "   - Go to Credentials → Create Credentials → OAuth client ID\n"
                    "   - Application type: Desktop app\n"
                    "   - Name: Any name (e.g., 'Twitch Clip Uploader')\n\n"
                    "3. Configure OAuth consent screen:\n"
                    "   - User type: External\n"
                    "   - Add your email as test user\n"
                    "   - Add scopes: youtube.upload\n\n"
                    "4. Download credentials:\n"
                    "   - Click download button\n"
                    "   - Save as 'client_secret.json'\n\n"
                    "5. After downloading, run this setup again and choose 'NO' to browse for the file"
                )
                
                messagebox.showinfo("Detailed Instructions", instructions)
                
            elif choice is False:  # Browse for file
                file_path = filedialog.askopenfilename(
                    title=f"Select client_secret.json for {cred_name}",
                    filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
                )
                
                if file_path:
                    try:
                        # Validate it's a proper credentials file
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if 'installed' not in data and 'web' not in data:
                                messagebox.showerror("Invalid File", 
                                                   "This doesn't appear to be a valid Google OAuth credentials file.")
                                return
                        
                        # Copy the file with the new name
                        shutil.copy2(file_path, client_secret_path)
                        
                        # Save credential info
                        self.youtube_handler.save_credential_info(safe_name, cred_name)
                        
                        self.log(f"✅ Added YouTube API credentials: {cred_name}")
                        messagebox.showinfo("Success", 
                                          f"Credentials '{cred_name}' added!\n\n"
                                          "Now you can add channels using these credentials.")
                        
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to add credentials:\n{str(e)}")
                        
        except Exception as e:
            self.log(f"❌ Error in add_new_credentials: {str(e)}")
            messagebox.showerror("Error", f"Failed to add credentials:\n{str(e)}")
    
    def manage_credentials(self):
        """View and manage existing credentials"""
        try:
            cred_info = self.youtube_handler.load_credential_info()
            
            if not cred_info:
                messagebox.showinfo("No Credentials", 
                                  "No credentials found.\n\n"
                                  "Please add credentials first.")
                return
            
            # Create window to show credentials
            manage_window = tk.Toplevel(self.root)
            manage_window.title("Manage YouTube Credentials")
            manage_window.geometry("500x300")
            manage_window.transient(self.root)
            manage_window.grab_set()
            
            tk.Label(manage_window, text="Available Credentials:", 
                    font=("Arial", 12, "bold")).pack(pady=10)
            
            # List frame
            list_frame = tk.Frame(manage_window)
            list_frame.pack(fill="both", expand=True, padx=20)
            
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side="right", fill="y")
            
            listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
            listbox.pack(side="left", fill="both", expand=True)
            scrollbar.config(command=listbox.yview)
            
            # Add credentials to list
            for cred in cred_info:
                listbox.insert(tk.END, f"{cred['display_name']} ({cred['channels']} channels)")
            
            # Buttons
            button_frame = tk.Frame(manage_window)
            button_frame.pack(pady=10)
            
            def delete_credential():
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select credentials to delete")
                    return
                
                idx = selection[0]
                cred = cred_info[idx]
                
                if messagebox.askyesno("Confirm Delete", 
                                     f"Delete credentials '{cred['display_name']}'?\n\n"
                                     "This will also remove associated channels."):
                    # Delete the credential file
                    try:
                        os.remove(os.path.join(YOUTUBE_CREDENTIALS_DIR, 
                                             f"client_secret_{cred['safe_name']}.json"))
                        # Update credential info
                        cred_info.pop(idx)
                        self.youtube_handler.save_all_credential_info(cred_info)
                        
                        # Remove associated channels
                        self.youtube_channels = [ch for ch in self.youtube_channels 
                                               if ch.get('credential_name') != cred['safe_name']]
                        self.youtube_handler.save_channels(self.youtube_channels)
                        self.refresh_youtube_channels()
                        
                        # Refresh list
                        listbox.delete(idx)
                        messagebox.showinfo("Deleted", f"Credentials '{cred['display_name']}' deleted")
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to delete: {str(e)}")
            
            tk.Button(button_frame, text="Delete Selected", 
                     command=delete_credential, bg="red", fg="white").pack(side="left", padx=5)
            tk.Button(button_frame, text="Close", 
                     command=manage_window.destroy).pack(side="left", padx=5)
                     
        except Exception as e:
            self.log(f"❌ Error in manage_credentials: {str(e)}")
            messagebox.showerror("Error", f"Failed to open credentials manager:\n{str(e)}")
    
    def add_youtube_channel(self):
        """Add a new YouTube channel"""
        if not self.youtube_handler.is_available():
            messagebox.showerror("Error", 
                               "YouTube libraries not installed!\n\n"
                               "Run these commands:\n"
                               "pip install google-auth google-auth-oauthlib google-auth-httplib2\n"
                               "pip install google-api-python-client")
            return
        
        try:
            # Load available credentials
            cred_info = self.youtube_handler.load_credential_info()
            
            if not cred_info:
                # No credentials found
                result = messagebox.askyesno(
                    "No Credentials Found",
                    "No YouTube API credentials found.\n\n"
                    "Would you like to set up credentials now?"
                )
                if result:
                    self.setup_youtube_api()
                return
            
            # If only one credential, use it
            if len(cred_info) == 1:
                selected_cred = cred_info[0]
            else:
                # Let user choose which credentials to use
                cred_window = tk.Toplevel(self.root)
                cred_window.title("Select Credentials")
                cred_window.geometry("400x300")
                cred_window.transient(self.root)
                cred_window.grab_set()
                
                tk.Label(cred_window, text="Select which Google account to use:", 
                        font=("Arial", 12, "bold")).pack(pady=10)
                
                # Variable to store selection
                selected_cred = None
                
                # List of credentials
                list_frame = tk.Frame(cred_window)
                list_frame.pack(fill="both", expand=True, padx=20)
                
                listbox = tk.Listbox(list_frame)
                listbox.pack(fill="both", expand=True)
                
                for cred in cred_info:
                    listbox.insert(tk.END, cred['display_name'])
                
                # Select first item
                if cred_info:
                    listbox.select_set(0)
                
                def on_select():
                    nonlocal selected_cred
                    selection = listbox.curselection()
                    if selection:
                        selected_cred = cred_info[selection[0]]
                        cred_window.destroy()
                
                button_frame = tk.Frame(cred_window)
                button_frame.pack(pady=10)
                
                tk.Button(button_frame, text="Select", command=on_select,
                         bg="green", fg="white").pack(side="left", padx=5)
                tk.Button(button_frame, text="Cancel", 
                         command=cred_window.destroy).pack(side="left", padx=5)
                
                # Wait for window to close
                self.root.wait_window(cred_window)
                
                if not selected_cred:
                    return
            
            # Now we have selected_cred, use it
            client_secret_path = os.path.join(YOUTUBE_CREDENTIALS_DIR, 
                                            f"client_secret_{selected_cred['safe_name']}.json")
            
            if not os.path.exists(client_secret_path):
                messagebox.showerror("Error", 
                                   f"Credentials file not found for {selected_cred['display_name']}")
                return
            
            # Check if user has reached channel limit
            if len(self.youtube_channels) >= 10:  # Increased limit for multiple accounts
                messagebox.showwarning(
                    "Channel Limit Reached",
                    f"You already have {len(self.youtube_channels)} channels connected.\n\n"
                    "To add a new channel, please remove an existing one first.\n"
                    "(Limit: 10 channels)"
                )
                return
            
            # Create a unique token file for each channel
            channel_name = simpledialog.askstring("Channel Name", 
                                                f"Using credentials: {selected_cred['display_name']}\n\n"
                                                "Enter a name for this channel\n(e.g., 'My Gaming Channel'):")
            if not channel_name:
                return
            
            # Ask user how they want to authenticate
            auth_choice = messagebox.askyesnocancel(
                "Authentication Method",
                "How would you like to authenticate with Google?\n\n"
                "YES - Automatically open browser (default)\n"
                "NO - Get link to copy/paste manually (for incognito/private browsing)\n"
                "CANCEL - Cancel authentication"
            )
            
            if auth_choice is None:  # Cancel
                return
            
            auth_mode = 'auto' if auth_choice else 'manual'
            
            result = self.youtube_handler.authenticate_channel(
                client_secret_path, channel_name, selected_cred['safe_name'],
                selected_cred['display_name'], auth_mode
            )
            
            if isinstance(result, dict) and result.get('type') == 'manual':
                # Manual authentication needed
                self.handle_manual_youtube_auth(result)
            else:
                channel_data, error = result
                if channel_data:
                    self.complete_channel_addition(channel_data)
                else:
                    messagebox.showerror("Error", f"Failed to add channel:\n{error}")
                    
        except Exception as e:
            self.log(f"❌ Error adding YouTube channel: {str(e)}")
            messagebox.showerror("Error", f"Failed to add channel:\n{str(e)}")
    
    def handle_manual_youtube_auth(self, auth_data):
        """Handle manual YouTube authentication"""
        # Create auth window for manual process
        auth_window = tk.Toplevel(self.root)
        auth_window.title("Manual Authentication")
        auth_window.geometry("700x500")
        auth_window.transient(self.root)
        auth_window.grab_set()
        
        # Instructions
        instructions = tk.Label(auth_window, 
                              text="Manual Authentication Process",
                              font=("Arial", 14, "bold"))
        instructions.pack(pady=10)
        
        # Step 1
        step1_frame = tk.LabelFrame(auth_window, text="Step 1: Copy Authentication URL", 
                                  font=("Arial", 10, "bold"))
        step1_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(step1_frame, 
                text="Copy the URL below and paste it in your browser (incognito mode is OK):",
                wraplength=650).pack(pady=5)
        
        # URL Text widget
        url_frame = tk.Frame(step1_frame)
        url_frame.pack(fill="x", padx=10, pady=5)
        
        url_text = tk.Text(url_frame, height=3, wrap=tk.WORD)
        url_scrollbar = ttk.Scrollbar(url_frame, command=url_text.yview)
        url_text.configure(yscrollcommand=url_scrollbar.set)
        
        url_text.insert("1.0", auth_data['auth_url'])
        url_text.configure(state='disabled')  # Make read-only
        
        url_text.pack(side="left", fill="both", expand=True)
        url_scrollbar.pack(side="right", fill="y")
        
        # Copy button
        def copy_url():
            self.root.clipboard_clear()
            self.root.clipboard_append(auth_data['auth_url'])
            messagebox.showinfo("Copied!", "URL copied to clipboard!")
        
        tk.Button(step1_frame, text="📋 Copy URL", command=copy_url,
                bg="lightblue").pack(pady=5)
        
        # Step 2
        step2_frame = tk.LabelFrame(auth_window, text="Step 2: Authorize in Browser", 
                                  font=("Arial", 10, "bold"))
        step2_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(step2_frame, 
                text="1. Paste the URL in your browser (any browser/mode)\n"
                     "2. Log in with your Google account\n"
                     "3. Grant permissions to the app\n"
                     "4. You'll see an authorization code",
                wraplength=650, justify="left").pack(pady=5)
        
        # Step 3
        step3_frame = tk.LabelFrame(auth_window, text="Step 3: Enter Authorization Code", 
                                  font=("Arial", 10, "bold"))
        step3_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(step3_frame, 
                text="Paste the authorization code from your browser here:").pack(pady=5)
        
        code_entry = tk.Entry(step3_frame, width=60)
        code_entry.pack(pady=5)
        
        # Result label
        result_label = tk.Label(auth_window, text="", fg="blue")
        result_label.pack(pady=10)
        
        def submit_code():
            code = code_entry.get().strip()
            if not code:
                messagebox.showwarning("No Code", "Please enter the authorization code!")
                return
            
            try:
                result_label.config(text="Authenticating...", fg="blue")
                auth_window.update()
                
                # Complete authentication
                channel_data, error = self.youtube_handler.complete_manual_auth(auth_data, code)
                
                if channel_data:
                    result_label.config(text="✅ Authentication successful!", fg="green")
                    messagebox.showinfo("Success", "Authentication successful!\n\nClick OK to continue.")
                    auth_window.destroy()
                    self.complete_channel_addition(channel_data)
                else:
                    result_label.config(text="❌ Authentication failed!", fg="red")
                    messagebox.showerror("Authentication Failed", 
                                       f"Failed to authenticate:\n{error}\n\n"
                                       "Please check the code and try again.")
                    
            except Exception as e:
                result_label.config(text="❌ Error occurred!", fg="red")
                messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        
        # Buttons
        button_frame = tk.Frame(auth_window)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="✅ Submit Code", command=submit_code,
                bg="green", fg="white", font=("Arial", 10)).pack(side="left", padx=10)
        
        tk.Button(button_frame, text="❌ Cancel", command=auth_window.destroy,
                bg="red", fg="white").pack(side="left", padx=10)
        
        # Tips
        tips_frame = tk.Frame(auth_window)
        tips_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(tips_frame, text="💡 Tips:", font=("Arial", 9, "bold")).pack(anchor="w")
        tk.Label(tips_frame, 
                text="• You can use incognito/private mode in any browser\n"
                     "• Make sure to use the correct Google account\n"
                     "• The code is usually displayed in a box after authorization\n"
                     "• The code may look like: 4/0AX4XfWj...",
                font=("Arial", 8), justify="left", fg="gray").pack(anchor="w")
    
    def complete_channel_addition(self, channel_data):
        """Complete the channel addition process"""
        # Check if channel already exists
        existing_channel = next((ch for ch in self.youtube_channels 
                               if ch['channel_id'] == channel_data['channel_id']), None)
        if existing_channel:
            messagebox.showwarning(
                "Channel Already Added",
                f"This channel is already connected as:\n{existing_channel['name']}\n\n"
                "You can only connect each YouTube channel once."
            )
            return
        
        self.youtube_channels.append(channel_data)
        self.youtube_handler.save_channels(self.youtube_channels)
        self.refresh_youtube_channels()
        
        # Reload automation schedules to update channel data
        self.automation_handler.load_schedules(self.youtube_channels)
        
        self.log(f"✅ Added YouTube channel: {channel_data['name']} ({channel_data['channel_title']})")
        
        # Ask if user wants to add more channels
        result = messagebox.askyesno(
            "Channel Added Successfully!",
            f"Successfully added channel:\n{channel_data['channel_title']}\n\n"
            f"You now have {len(self.youtube_channels)} channel(s) connected.\n\n"
            "Would you like to add another channel?"
        )
        
        if result:
            # User wants to add more channels
            self.root.after(100, self.add_youtube_channel)
        else:
            # Show a friendly completion message
            self.log(f"📺 Total channels connected: {len(self.youtube_channels)}")
            messagebox.showinfo(
                "Setup Complete",
                f"Great! You have {len(self.youtube_channels)} channel(s) ready for uploads.\n\n"
                "You can now:\n"
                "• Download clips and upload them\n"
                "• Add more channels from same or different Google accounts\n"
                "• Remove channels if needed\n"
                "• Set up automation schedules"
            )
    
    def remove_youtube_channel(self):
        """Remove selected YouTube channel"""
        try:
            selection = self.channels_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a channel to remove")
                return
            
            idx = selection[0]
            channel = self.youtube_channels[idx]
            
            result = messagebox.askyesno("Confirm Removal", 
                                       f"Remove channel '{channel['name']}'?\n\n"
                                       f"Channel: {channel['channel_title']}")
            if result:
                # Remove token file
                if os.path.exists(channel['token_file']):
                    try:
                        os.remove(channel['token_file'])
                    except:
                        pass  # File might be in use or already deleted
                
                # Remove from list
                self.youtube_channels.pop(idx)
                self.youtube_handler.save_channels(self.youtube_channels)
                self.refresh_youtube_channels()
                
                self.log(f"✅ Removed YouTube channel: {channel['name']}")
                
                # Show success message with current count
                count = len(self.youtube_channels)
                if count == 0:
                    msg = "Channel removed! No channels connected."
                elif count == 1:
                    msg = "Channel removed! 1 channel remaining."
                else:
                    msg = f"Channel removed! {count} channels remaining."
                
                messagebox.showinfo("Channel Removed", msg)
                
        except Exception as e:
            self.log(f"❌ Error removing channel: {str(e)}")
            messagebox.showerror("Error", f"Failed to remove channel:\n{str(e)}")
    
    def refresh_youtube_channels(self):
        """Refresh the channels listbox"""
        try:
            self.channels_listbox.delete(0, tk.END)
            
            for channel in self.youtube_channels:
                # Show which credentials the channel uses
                credential_info = ""
                if 'credential_display' in channel:
                    credential_info = f" [{channel['credential_display']}]"
                display_text = f"{channel['name']} ({channel['channel_title']}){credential_info}"
                self.channels_listbox.insert(tk.END, display_text)
            
            # Update channel count label
            count = len(self.youtube_channels)
            if count == 0:
                self.channels_count_label.config(text="No channels connected", fg="gray")
            elif count == 1:
                self.channels_count_label.config(text="1 channel connected", fg="green")
            else:
                self.channels_count_label.config(text=f"{count} channels connected", fg="green")
        except Exception as e:
            self.log(f"⚠️ Error refreshing channels: {str(e)}")
    
    def on_excel_toggle(self):
        """Enable/disable Excel configuration based on checkbox"""
        if self.use_excel_var.get():
            for widget in self.excel_config_frame.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Button):
                            child.configure(state='normal')
                else:
                    widget.configure(state='normal')
        else:
            for widget in self.excel_config_frame.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Button):
                            child.configure(state='disabled')
    
    def choose_excel_file(self):
        """Let user select Excel file"""
        filepath = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*"))
        )
        
        if filepath:
            self.excel_handler.excel_path = filepath
            self.excel_label.config(text=f"Selected: {os.path.basename(filepath)}")
            self.log(f"✅ Excel file selected: {os.path.basename(filepath)}")
            
            # Load and clean the Excel file
            success, message = self.excel_handler.load_excel_file(filepath)
            if success:
                self.excel_status.config(text=message, fg="green")
            else:
                self.excel_status.config(text=message, fg="red")
    
    def create_new_excel(self):
        """Create a new Excel file"""
        filepath = filedialog.asksaveasfilename(
            title="Create New Excel File",
            defaultextension=".xlsx",
            filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*"))
        )
        
        if filepath:
            if self.excel_handler.create_new_excel(filepath):
                self.excel_label.config(text=f"Created: {os.path.basename(filepath)}")
                self.log(f"✅ Created new Excel file: {os.path.basename(filepath)}")
                
                # Load it
                success, message = self.excel_handler.load_excel_file(filepath)
                if success:
                    self.excel_status.config(text=message, fg="green")
                
                messagebox.showinfo("Success", "Excel file created successfully!")
            else:
                self.log(f"❌ Error creating Excel file")
                messagebox.showerror("Error", "Could not create Excel file")
    
    def on_duration_change(self):
        """Show/hide custom duration inputs based on selection"""
        if self.duration_var.get() == "custom":
            self.custom_duration_frame.pack(pady=5)
        else:
            self.custom_duration_frame.pack_forget()
    
    def update_caption_description(self, *args):
        """Update caption style description"""
        style = self.caption_style_var.get()
        self.caption_desc.config(text=CAPTION_DESCRIPTIONS.get(style, ""))
    
    def on_format_change(self):
        """Show/hide caption options based on format selection"""
        if self.format_var.get() == "portrait":
            # Show caption frame and blur frame for portrait
            format_frames = [w for w in self.main_frame.scrollable_frame.winfo_children() 
                           if isinstance(w, tk.LabelFrame) and "Choose Video Format" in w.cget("text")]
            if format_frames:
                self.caption_frame.pack(pady=10, padx=20, fill="x", after=format_frames[0])
                # Show blur frame inside format frame
                self.portrait_blur_frame.pack(pady=10, padx=20, fill="x")
                # Update blur mode display
                self.on_blur_mode_change()
        else:
            # Hide caption frame and blur frame for landscape
            self.caption_frame.pack_forget()
            self.portrait_blur_frame.pack_forget()
    
    def on_caption_toggle(self):
        """Enable/disable style options based on caption checkbox"""
        is_checked = self.captions_var.get()
        new_state = 'normal' if is_checked else 'disabled'
        
        # Toggle all children of the style frame and other controls
        for widget in self.style_frame.winfo_children():
            # This is a bit tricky since some children are frames themselves
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    if hasattr(child, 'configure'):
                        child.configure(state=new_state)
            if hasattr(widget, 'configure'):
                widget.configure(state=new_state)
                
        self.animation_menu.configure(state='readonly' if is_checked else 'disabled')
    
    def choose_folder(self):
        """Let user pick where to save clips"""
        folder = filedialog.askdirectory()
        if folder:
            self.save_folder = folder
            self.folder_label.config(text=f"Save to: {folder}")
            self.log("✅ Save folder selected: " + folder)
    
    def log(self, message):
        """Write messages to the log box"""
        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.root.update_idletasks()
    
    def check_requirements(self):
        """Check if required tools are installed"""
        streamlink_ok = self.downloader.check_streamlink()
        ffmpeg_ok = self.downloader.check_ffmpeg()
        whisper_ok = self.video_processor.check_whisper()
        moviepy_ok = self.video_processor.check_moviepy()
        openpyxl_ok = self.excel_handler.is_available()
        youtube_ok = self.youtube_handler.is_available()
        gemini_ok = self.gemini_handler.is_available()
        
        # Update UI labels
        self.streamlink_label.config(text="✅ Streamlink" if streamlink_ok else "❌ Streamlink", 
                                   fg="green" if streamlink_ok else "red")
        self.ffmpeg_label.config(text="✅ FFmpeg" if ffmpeg_ok else "❌ FFmpeg", 
                               fg="green" if ffmpeg_ok else "red")
        self.whisper_label.config(text="✅ Whisper" if whisper_ok else "⚠️ Whisper", 
                                fg="green" if whisper_ok else "orange")
        self.moviepy_label.config(text="✅ MoviePy" if moviepy_ok else "⚠️ MoviePy", 
                                fg="green" if moviepy_ok else "orange")
        self.openpyxl_label.config(text="✅ openpyxl" if openpyxl_ok else "⚠️ openpyxl", 
                                 fg="green" if openpyxl_ok else "orange")
        self.youtube_label.config(text="✅ YouTube" if youtube_ok else "⚠️ YouTube", 
                                fg="green" if youtube_ok else "orange")
        
        # Check Gemini
        if gemini_ok:
            if self.gemini_handler.api_key:
                if self.gemini_handler.model:
                    self.gemini_label.config(text="✅ Gemini AI", fg="green")
                else:
                    self.gemini_label.config(text="⚠️ Gemini (Model Error)", fg="orange")
            else:
                self.gemini_label.config(text="⚠️ Gemini (No Key)", fg="orange")
        else:
            self.gemini_label.config(text="⚠️ Gemini", fg="orange")
            self.log("⚠️ Gemini not found. AI features require: pip install google-generativeai")
        
        # Log missing requirements
        if not streamlink_ok:
            self.log("⚠️ Streamlink not found. Run: pip install streamlink")
        if not ffmpeg_ok:
            self.log("⚠️ FFmpeg not found. Download from ffmpeg.org")
        if not whisper_ok:
            self.log("⚠️ Whisper not found. Captions require: pip install openai-whisper")
        if not moviepy_ok:
            self.log("⚠️ MoviePy not found. Professional captions require: pip install moviepy")
        if not openpyxl_ok:
            self.log("⚠️ openpyxl not found. Excel tracking requires: pip install openpyxl")
        if not youtube_ok:
            self.log("⚠️ YouTube libraries not found. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        
        return streamlink_ok and ffmpeg_ok
    
    def get_duration_range(self):
        """Get the selected duration range in seconds"""
        duration_setting = self.duration_var.get()
        
        if duration_setting == "all":
            return None, None
        elif duration_setting == "0-15":
            return 0, 15
        elif duration_setting == "15-30":
            return 15, 30
        elif duration_setting == "30-60":
            return 30, 60
        elif duration_setting == "60+":
            return 60, float('inf')
        elif duration_setting == "custom":
            try:
                min_dur = int(self.min_duration_entry.get())
                max_dur = int(self.max_duration_entry.get())
                return min_dur, max_dur
            except ValueError:
                self.log("⚠️ Invalid custom duration range, using all durations")
                return None, None
        
        return None, None
    
    def stop_download_process(self):
        """Stop the download process"""
        self.stop_download = True
        self.log("🛑 Stopping download process...")
        self.status_label.config(text="Stopping...", fg="orange")
        
        # Force update the UI
        self.root.update_idletasks()
        
        # Wait a bit for the thread to stop
        if self.download_thread and self.download_thread.is_alive():
            # Give the thread 2 seconds to stop gracefully
            self.download_thread.join(timeout=2)
            
            if self.download_thread.is_alive():
                self.log("⚠️ Download thread still running, please wait...")
    
    def start_download(self):
        """Start downloading clips in a separate thread"""
        # Check requirements
        if not self.save_folder:
            messagebox.showerror("Error", "Please select a save folder first!")
            return
        
        # Check internet connection
        if not check_internet_connection():
            messagebox.showerror("No Internet", "No internet connection detected!\n\nPlease check your connection and try again.")
            return
        
        # Reset stop flag
        self.stop_download = False
        
        # Clear downloaded videos list
        self.downloaded_videos = []
        
        # Update button states
        self.download_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        
        # Start download in thread
        self.download_thread = threading.Thread(target=self.download_process)
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def download_process(self):
        """Main download process"""
        try:
            # Get user inputs
            game_url = self.url_entry.get()
            min_views = int(self.min_views_entry.get())
            max_views = int(self.max_views_entry.get()) if self.max_views_entry.get() else None
            days_back = int(self.days_entry.get())
            clip_count = int(self.clips_count_entry.get())
            
            # Get language selection
            language_name = self.language_var.get()
            language_code = self.language_codes[language_name]
            
            # Get duration range
            min_duration, max_duration = self.get_duration_range()
            
            # Update status
            self.status_label.config(text="Finding clips...", fg="blue")
            self.log("\n🔍 Starting new search...")
            
            # Get game ID
            game_id, game_name = self.twitch_api.get_game_id(game_url)
            if not game_id:
                self.log("❌ Invalid game URL!")
                self.status_label.config(text="Invalid game URL!", fg="red")
                return
            
            # Store game name for YouTube upload
            self.current_game_name = game_name
            
            # Get clips
            self.log(f"🔍 Searching for {clip_count} clips from the last {days_back} days...")
            if language_code != 'all':
                self.log(f"   Language filter: {language_name}")
            
            # Load Excel if enabled
            if self.use_excel_var.get() and self.excel_handler.excel_path:
                success, message = self.excel_handler.load_excel_file(self.excel_handler.excel_path)
                if success:
                    self.log(f"📊 {message}")
            
            clips, game_name = self.twitch_api.get_clips(
                game_id, game_name, min_views, max_views, 
                days_back, clip_count, language_code,
                min_duration, max_duration,
                self.excel_handler.check_if_downloaded if self.use_excel_var.get() else None,
                self.log,
                lambda: self.stop_download
            )
            
            if not clips:
                self.log("❌ No clips found matching your criteria!")
                self.status_label.config(text="No clips found!", fg="red")
                return
            
            # Set up progress bar
            self.progress['maximum'] = len(clips)
            self.progress['value'] = 0
            
            # Download each clip
            successful = 0
            failed_downloads = []
            
            for i, clip in enumerate(clips):
                if self.stop_download:
                    self.log("⏹️ Download stopped by user")
                    break
                
                # Check internet connection periodically
                if i % 5 == 0 and not check_internet_connection():
                    self.log("❌ Lost internet connection! Waiting...")
                    self.status_label.config(text="No internet connection...", fg="red")
                    
                    # Wait for internet to come back
                    wait_time = 0
                    while not check_internet_connection() and wait_time < 300 and not self.stop_download:
                        time.sleep(10)
                        wait_time += 10
                    
                    if check_internet_connection():
                        self.log("✅ Internet connection restored!")
                    else:
                        self.log("❌ Internet connection timeout. Stopping downloads.")
                        break
                    
                clip_title = sanitize_filename(clip['title'])
                
                # Create filename based on format
                if self.format_var.get() == "portrait":
                    filename = f"{i+1}_{clip_title[:30]}_{clip['id']}_portrait.mp4"
                else:
                    filename = f"{i+1}_{clip_title[:30]}_{clip['id']}.mp4"
                
                save_path = os.path.join(self.save_folder, filename)
                
                # Check if file already exists
                if os.path.exists(save_path):
                    self.log(f"⏭️ Skipping (already exists): {clip['title']}")
                    successful += 1
                    self.downloaded_videos.append(save_path)
                    self.progress['value'] = i + 1
                    continue
                
                # Update status
                self.status_label.config(text=f"Downloading {i+1}/{len(clips)}: {clip['title'][:50]}...", fg="blue")
                
                # Download the clip
                temp_path = os.path.join(self.save_folder, f"temp_{clip['id']}.mp4")
                if self.downloader.download_clip(clip, temp_path, self.log, lambda: self.stop_download):
                    # Convert to portrait if selected
                    if self.format_var.get() == "portrait":
                        # Setup caption settings
                        caption_settings = {
                            'style': self.caption_style_var.get(),
                            'animation': self.caption_animation_var.get(),
                            'position': self.caption_position_var.get()
                        }
                        
                        # Use the safe conversion method
                        if self.safe_convert_to_portrait(
                            temp_path, save_path, 
                            add_captions=self.captions_var.get(),
                            blur_mode=self.portrait_blur_mode_var.get(),
                            blur_top=self.portrait_blur_top_var.get(),
                            blur_bottom=self.portrait_blur_bottom_var.get(),
                            caption_settings=caption_settings,
                            log_func=self.log
                        ):
                            try:
                                os.remove(temp_path)
                            except:
                                pass
                            successful += 1
                            self.downloaded_videos.append(save_path)
                            # Add to Excel
                            if self.use_excel_var.get():
                                self.excel_handler.add_clip(clip, game_name)
                        else:
                            self.log("❌ Failed to convert to portrait format")
                            failed_downloads.append(clip['title'])
                            try:
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                            except:
                                pass
                    else:
                        # Just move the file for landscape
                        try:
                            shutil.move(temp_path, save_path)
                            successful += 1
                            self.downloaded_videos.append(save_path)
                            # Add to Excel
                            if self.use_excel_var.get():
                                self.excel_handler.add_clip(clip, game_name)
                        except Exception as e:
                            self.log(f"❌ Error moving file: {str(e)}")
                            failed_downloads.append(clip['title'])
                else:
                    failed_downloads.append(clip['title'])
                
                # Update progress
                self.progress['value'] = i + 1
                self.root.update_idletasks()
            
            # Final status
            if self.stop_download:
                self.status_label.config(text=f"Stopped! Downloaded {successful} clips", fg="orange")
            else:
                self.status_label.config(text=f"Complete! Downloaded {successful}/{len(clips)} clips", fg="green")
                self.log(f"\n✅ Download complete! {successful}/{len(clips)} clips saved to {self.save_folder}")
                
                if failed_downloads:
                    self.log(f"\n❌ Failed downloads ({len(failed_downloads)}):")
                    for title in failed_downloads[:5]:  # Show first 5
                        self.log(f"   - {title}")
                    if len(failed_downloads) > 5:
                        self.log(f"   ... and {len(failed_downloads) - 5} more")
                
                # Ask if user wants to upload to YouTube
                if successful > 0 and self.youtube_channels:
                    result = messagebox.askyesno("Upload to YouTube?", 
                                               f"Downloaded {successful} clips!\n\n"
                                               "Do you want to upload them to YouTube now?")
                    if result:
                        self.root.after(100, self.show_upload_window)
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
            self.status_label.config(text="Error occurred!", fg="red")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        
        finally:
            # Reset button states
            self.download_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.stop_download = False
    
    def show_upload_window(self):
        """Show window for selecting videos to upload"""
        if not self.downloaded_videos:
            messagebox.showinfo("No Videos", "No videos to upload!")
            return
        
        if not self.youtube_channels:
            messagebox.showwarning("No Channels", 
                                 "Please add at least one YouTube channel first!")
            return
        
        # Create upload window
        YouTubeUploadWindow(self, self.downloaded_videos, 
                          self.youtube_channels, self.current_game_name)