import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import calendar
from core.automation import AutomationSchedule
from utils.helpers import convert_12h_to_24h, convert_24h_to_12h, get_ordered_days_from_today, calculate_time_until

class AutomationUI:
    """UI components for automation features"""
    
    def __init__(self, parent):
        self.parent = parent
        
    def create_schedule_window(self, youtube_channels, save_folder, game_url, 
                             edit_mode=False, existing_schedule=None, schedule_index=None):
        """Create window for adding/editing automation schedule"""
        if not youtube_channels:
            messagebox.showwarning("No Channels", "Please add at least one YouTube channel first!")
            return
        
        if not save_folder:
            messagebox.showwarning("No Folder", "Please select a save folder first!")
            return
        
        # Determine window title and mode
        if edit_mode:
            window_title = "Edit Automation Schedule"
            button_text = "💾 Update Schedule"
        elif existing_schedule:
            window_title = "Duplicate Automation Schedule"
            button_text = "💾 Create Duplicate"
        else:
            window_title = "Add Automation Schedule"
            button_text = "💾 Save Schedule"
        
        # Create new schedule window
        schedule_window = tk.Toplevel(self.parent.root)
        schedule_window.title(window_title)
        schedule_window.geometry("800x1400")
        schedule_window.transient(self.parent.root)
        schedule_window.grab_set()
        
        # Create scrollable frame
        canvas = tk.Canvas(schedule_window)
        scrollbar = ttk.Scrollbar(schedule_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create or use existing schedule object
        if existing_schedule:
            new_schedule = existing_schedule
        else:
            new_schedule = AutomationSchedule()
        
        # Channel selection
        tk.Label(scrollable_frame, text="Select YouTube Channel:", font=("Arial", 10, "bold")).pack(pady=5)
        channel_var = tk.StringVar()
        
        # Set default channel value
        if existing_schedule and existing_schedule.channel_name:
            channel_var.set(existing_schedule.channel_name)
        else:
            channel_var.set(youtube_channels[0]['name'])
        
        channel_menu = ttk.Combobox(scrollable_frame, textvariable=channel_var,
                                   values=[ch['name'] for ch in youtube_channels],
                                   state="readonly", width=30)
        channel_menu.pack()
        
        # Video format and count
        format_frame = tk.LabelFrame(scrollable_frame, text="Video Formats & Counts (Per Day)", 
                                   font=("Arial", 10, "bold"), pady=10, padx=10)
        format_frame.pack(pady=10, fill="x", padx=20)
        
        # Landscape videos
        landscape_frame = tk.Frame(format_frame)
        landscape_frame.pack(pady=5)
        
        tk.Label(landscape_frame, text="🖥️ Landscape videos per day:").pack(side=tk.LEFT, padx=5)
        landscape_count_var = tk.IntVar(value=existing_schedule.landscape_videos_per_day if existing_schedule else 0)
        landscape_spinbox = tk.Spinbox(landscape_frame, from_=0, to=10, 
                                     textvariable=landscape_count_var, width=10)
        landscape_spinbox.pack(side=tk.LEFT, padx=5)
        
        # Portrait videos
        portrait_frame = tk.Frame(format_frame)
        portrait_frame.pack(pady=5)
        
        tk.Label(portrait_frame, text="📱 Portrait videos per day:").pack(side=tk.LEFT, padx=5)
        portrait_count_var = tk.IntVar(value=existing_schedule.portrait_videos_per_day if existing_schedule else 0)
        portrait_spinbox = tk.Spinbox(portrait_frame, from_=0, to=10, 
                                    textvariable=portrait_count_var, width=10)
        portrait_spinbox.pack(side=tk.LEFT, padx=5)
        
        # Total videos display
        total_label = tk.Label(format_frame, text="Total: 0 videos per day", 
                             font=("Arial", 9), fg="blue")
        total_label.pack(pady=5)
        
        def update_total(*args):
            total = landscape_count_var.get() + portrait_count_var.get()
            total_label.config(text=f"Total: {total} videos per day")
        
        landscape_count_var.trace('w', update_total)
        portrait_count_var.trace('w', update_total)
        update_total()  # Initial update
        
        # Language Filter for Automation
        language_frame = tk.LabelFrame(scrollable_frame, text="🌍 Language Filter", 
                                     font=("Arial", 10, "bold"), pady=10, padx=10)
        language_frame.pack(pady=10, fill="x", padx=20)
        
        lang_inner = tk.Frame(language_frame)
        lang_inner.pack()
        
        tk.Label(lang_inner, text="Select Language:").pack(side=tk.LEFT, padx=5)
        
        # Import LANGUAGES from config
        from config import LANGUAGES
        language_var = tk.StringVar()
        
        # Set default language value
        if existing_schedule and hasattr(existing_schedule, 'language_filter'):
            # Find display name for the language code
            lang_display = next((lang[0] for lang in LANGUAGES if lang[1] == existing_schedule.language_filter), "All Languages")
            language_var.set(lang_display)
        else:
            language_var.set("All Languages")
        
        language_menu = ttk.Combobox(lang_inner, textvariable=language_var,
                                   values=[lang[0] for lang in LANGUAGES],
                                   state="readonly", width=25)
        language_menu.pack(side=tk.LEFT, padx=5)
        
        # Store language codes
        language_codes = {lang[0]: lang[1] for lang in LANGUAGES}
        
        # Language explanation
        lang_info = tk.Label(language_frame, 
                           text="ℹ️ Uses same detection as main app: broadcaster language + smart title detection",
                           font=("Arial", 8), fg="blue")
        lang_info.pack(pady=5)
        
        # Gemini AI Settings
        gemini_frame = tk.LabelFrame(scrollable_frame, text="🤖 Gemini AI Title & Description Generation", 
                                   font=("Arial", 10, "bold"), pady=10, padx=10)
        gemini_frame.pack(pady=10, fill="x", padx=20)
        
        # Enable Gemini checkbox
        use_gemini_var = tk.BooleanVar(value=getattr(existing_schedule, 'use_gemini_titles', False) if existing_schedule else False)
        gemini_check = tk.Checkbutton(gemini_frame, 
                                     text="Use Gemini AI to auto-generate titles and descriptions",
                                     variable=use_gemini_var,
                                     font=("Arial", 10))
        gemini_check.pack(anchor="w")
        
        # Check if Gemini is available
        if self.parent.gemini_handler.is_available() and self.parent.gemini_handler.api_key:
            gemini_status_text = "✅ Gemini AI is configured and ready"
            gemini_status_color = "green"
        elif self.parent.gemini_handler.is_available() and not self.parent.gemini_handler.api_key:
            gemini_status_text = "⚠️ Gemini AI not configured - go to Settings to add API key"
            gemini_status_color = "orange"
            use_gemini_var.set(False)
            gemini_check.config(state="disabled")
        else:
            gemini_status_text = "⚠️ Gemini AI library not installed - pip install google-generativeai"
            gemini_status_color = "orange"
            use_gemini_var.set(False)
            gemini_check.config(state="disabled")
        
        tk.Label(gemini_frame, text=gemini_status_text, 
                font=("Arial", 9), fg=gemini_status_color).pack(pady=5)
        
        # Add note about working without Gemini
        tk.Label(gemini_frame, 
                text="Note: Automation works without Gemini AI - it will use default titles",
                font=("Arial", 8), fg="gray").pack()
        
        # Gemini creativity level
        creativity_frame = tk.Frame(gemini_frame)
        creativity_frame.pack(pady=5)
        
        tk.Label(creativity_frame, text="Creativity Level:").pack(side=tk.LEFT, padx=5)
        creativity_var = tk.StringVar(value=getattr(existing_schedule, 'gemini_creativity', "balanced") if existing_schedule else "balanced")
        
        creativity_options = [
            ("Conservative", "conservative"),
            ("Balanced", "balanced"),
            ("Creative", "creative")
        ]
        
        for text, value in creativity_options:
            tk.Radiobutton(creativity_frame, text=text, variable=creativity_var, 
                         value=value).pack(side=tk.LEFT, padx=5)
        
        # Portrait caption settings
        caption_frame = tk.LabelFrame(scrollable_frame, text="📱 Portrait Video Caption & Blur Settings", 
                                    font=("Arial", 10, "bold"), pady=10, padx=10)
        caption_frame.pack(pady=10, fill="x", padx=20)
        
        # Enable captions
        portrait_captions_var = tk.BooleanVar(value=getattr(existing_schedule, 'portrait_captions_enabled', True) if existing_schedule else True)
        tk.Checkbutton(caption_frame, text="Add captions to portrait videos",
                      variable=portrait_captions_var).pack(anchor="w")
        
        # Caption style
        style_frame = tk.Frame(caption_frame)
        style_frame.pack(pady=5)
        
        tk.Label(style_frame, text="Caption Style:").pack(side=tk.LEFT, padx=5)
        caption_style_var = tk.StringVar(value=getattr(existing_schedule, 'portrait_caption_style', "modern") if existing_schedule else "modern")
        styles = [("TikTok", "modern"), ("Classic", "classic"), ("Bold", "bold"), 
                 ("Gadzhi", "gadzhi"), ("Hormozi", "hormozi")]
        style_menu = ttk.Combobox(style_frame, textvariable=caption_style_var,
                                values=[s[0] for s in styles], state="readonly", width=15)
        style_menu.pack(side=tk.LEFT, padx=5)
        
        # Caption animation
        animation_frame = tk.Frame(caption_frame)
        animation_frame.pack(pady=5)
        
        tk.Label(animation_frame, text="Animation:").pack(side=tk.LEFT, padx=5)
        caption_animation_var = tk.StringVar(value=getattr(existing_schedule, 'portrait_caption_animation', "pop") if existing_schedule else "pop")
        animation_menu = ttk.Combobox(animation_frame, textvariable=caption_animation_var,
                                    values=["pop", "fade", "slide", "zoom", "typewriter", "bounce", "Karaoke Style"],
                                    state="readonly", width=15)
        animation_menu.pack(side=tk.LEFT, padx=5)
        
        # Caption position
        position_frame = tk.Frame(caption_frame)
        position_frame.pack(pady=5)
        
        tk.Label(position_frame, text="Position:").pack(side=tk.LEFT, padx=5)
        caption_position_var = tk.StringVar(value=getattr(existing_schedule, 'portrait_caption_position', "center") if existing_schedule else "center")
        position_menu = ttk.Combobox(position_frame, textvariable=caption_position_var,
                                   values=["center", "top", "bottom"],
                                   state="readonly", width=15)
        position_menu.pack(side=tk.LEFT, padx=5)
        
        # Portrait Blur Settings
        blur_settings_frame = tk.LabelFrame(caption_frame, text="🌫️ Portrait Blur Settings", 
                                          font=("Arial", 9, "bold"), pady=5)
        blur_settings_frame.pack(pady=10, fill="x")
        
        blur_mode_var = tk.StringVar(value="custom" if (existing_schedule and (getattr(existing_schedule, 'portrait_blur_top', 0) > 0 or getattr(existing_schedule, 'portrait_blur_bottom', 0) > 0)) else "standard")
        tk.Radiobutton(blur_settings_frame, text="Standard Blur (Full Background)", 
                      variable=blur_mode_var, value="standard").pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(blur_settings_frame, text="Custom Blur Percentage", 
                      variable=blur_mode_var, value="custom").pack(side=tk.LEFT, padx=10)
        
        # Blur percentage inputs
        blur_percent_frame = tk.Frame(blur_settings_frame)
        blur_percent_frame.pack(pady=5)
        
        tk.Label(blur_percent_frame, text="Top:").pack(side=tk.LEFT, padx=5)
        blur_top_var = tk.IntVar(value=getattr(existing_schedule, 'portrait_blur_top', 10) if existing_schedule else 10)
        tk.Spinbox(blur_percent_frame, from_=0, to=30, textvariable=blur_top_var, 
                  width=5).pack(side=tk.LEFT, padx=2)
        tk.Label(blur_percent_frame, text="%").pack(side=tk.LEFT, padx=(0,10))
        
        tk.Label(blur_percent_frame, text="Bottom:").pack(side=tk.LEFT, padx=5)
        blur_bottom_var = tk.IntVar(value=getattr(existing_schedule, 'portrait_blur_bottom', 10) if existing_schedule else 10)
        tk.Spinbox(blur_percent_frame, from_=0, to=30, textvariable=blur_bottom_var, 
                  width=5).pack(side=tk.LEFT, padx=2)
        tk.Label(blur_percent_frame, text="%").pack(side=tk.LEFT)
        
        # Better explanation for proportional scaling
        blur_info = tk.Label(blur_percent_frame, 
                           text="💡 Video will SCALE UP proportionally to fill the entire clear area\n"
                                "Example: 10% top + 10% bottom = video fills 80% middle area completely\n"
                                "Perfect for creating engaging portrait content!",
                           font=("Arial", 9), fg="blue", justify="center")
        blur_info.pack(pady=8)
        
        # Dynamic clear area display
        clear_area_label = tk.Label(blur_percent_frame, text="Clear area: 80%", 
                                  font=("Arial", 10, "bold"), fg="green")
        clear_area_label.pack(pady=2)
        
        def update_clear_area(*args):
            """Update the clear area percentage display"""
            top_val = blur_top_var.get()
            bottom_val = blur_bottom_var.get()
            clear_percent = 100 - top_val - bottom_val
            clear_area_label.config(text=f"Clear area: {clear_percent}% (video scales to fill this)")
            
            # Change color based on clear area size
            if clear_percent >= 70:
                clear_area_label.config(fg="green")
            elif clear_percent >= 50:
                clear_area_label.config(fg="orange") 
            else:
                clear_area_label.config(fg="red")
        
        # Bind the update function to blur variables
        blur_top_var.trace('w', update_clear_area)
        blur_bottom_var.trace('w', update_clear_area)
        
        # Initial update
        update_clear_area()
        
        # Weekly Schedule
        schedule_frame = tk.LabelFrame(scrollable_frame, text="📅 Weekly Upload Schedule", 
                                     font=("Arial", 10, "bold"), pady=10, padx=10)
        schedule_frame.pack(pady=10, fill="x", padx=20)
        
        # Get current date and time info
        now = datetime.now()
        current_day = now.strftime('%A')
        current_time = now.strftime("%I:%M %p")
        
        # Header with current date/time
        header_frame = tk.Frame(schedule_frame)
        header_frame.pack(fill="x", pady=5)
        
        tk.Label(header_frame, text=f"Today is {current_day}, {current_time}", 
                font=("Arial", 11, "bold"), fg="blue").pack()
        
        tk.Label(schedule_frame, text="Set upload times for each day (12-hour format, comma-separated):", 
                font=("Arial", 9)).pack(pady=5)
        tk.Label(schedule_frame, text="Example: 9:00 AM, 2:00 PM, 8:00 PM", 
                font=("Arial", 8), fg="gray").pack()
        
        # Store day widgets
        day_widgets = {}
        
        # Get ordered days starting from today
        ordered_days = get_ordered_days_from_today()
        
        # Function to update preview
        def update_preview(day, entry_widget, preview_widget):
            """Update the preview for when the next upload will be"""
            times_str = entry_widget.get()
            if times_str.strip():
                times = []
                for time_str in times_str.split(','):
                    time_str = time_str.strip()
                    if time_str:
                        time_24h = convert_12h_to_24h(time_str)
                        if time_24h:
                            times.append(time_24h)
                
                if times:
                    # Find the next upcoming time
                    next_time = None
                    for time_24h in sorted(times):
                        time_info = calculate_time_until(day, time_24h)
                        next_time = time_info
                        break
                    
                    if next_time:
                        preview_widget.config(text=f"→ Next: {next_time}", fg="green")
                    else:
                        preview_widget.config(text="", fg="gray")
                else:
                    preview_widget.config(text="", fg="gray")
            else:
                preview_widget.config(text="", fg="gray")
        
        # Create input for each day (starting from today)
        for i, day in enumerate(ordered_days):
            day_frame = tk.Frame(schedule_frame)
            day_frame.pack(fill="x", pady=3, padx=10)
            
            # Add background color for today
            if i == 0:  # Today
                day_frame.configure(bg="#E8F4FD")  # Light blue background
                day_text = f"📍 {day} (TODAY):"
                font_style = ("Arial", 10, "bold")
                fg_color = "blue"
            else:
                day_text = f"{day}:"
                font_style = ("Arial", 9, "bold")
                fg_color = "black"
            
            # Checkbox to enable/disable day
            enabled_var = tk.BooleanVar()
            
            # Set default value from existing schedule
            if existing_schedule and day in existing_schedule.weekly_schedule:
                enabled_var.set(existing_schedule.weekly_schedule[day]['enabled'])
            else:
                enabled_var.set(True)
            
            check = tk.Checkbutton(day_frame, text=day_text, 
                                 variable=enabled_var, font=font_style,
                                 fg=fg_color, width=18, anchor="w")
            check.pack(side=tk.LEFT)
            
            # For today, add background to checkbox too
            if i == 0:
                check.configure(bg="#E8F4FD", activebackground="#E8F4FD")
            
            # Time entry
            time_entry = tk.Entry(day_frame, width=35)
            
            # Set default times from existing schedule
            if existing_schedule and day in existing_schedule.weekly_schedule:
                existing_times = existing_schedule.weekly_schedule[day]['times']
                if existing_times:
                    # Convert 24h times back to 12h format
                    display_times = []
                    for time_24h in existing_times:
                        time_12h = convert_24h_to_12h(time_24h)
                        display_times.append(time_12h)
                    time_entry.insert(0, ', '.join(display_times))
                else:
                    # Default times for new schedules
                    if i == 0:  # Today - suggest times starting from next hour
                        next_hour = (now.hour + 1) % 24
                        if next_hour < 12:
                            suggested_time = f"{next_hour}:00 AM" if next_hour > 0 else "12:00 AM"
                        else:
                            suggested_time = f"{next_hour - 12}:00 PM" if next_hour > 12 else "12:00 PM"
                        time_entry.insert(0, f"{suggested_time}, 2:00 PM, 8:00 PM")
                    else:
                        time_entry.insert(0, "9:00 AM, 2:00 PM, 8:00 PM")
            else:
                # Default times for new schedules
                if i == 0:  # Today - suggest times starting from next hour
                    next_hour = (now.hour + 1) % 24
                    if next_hour < 12:
                        suggested_time = f"{next_hour}:00 AM" if next_hour > 0 else "12:00 AM"
                    else:
                        suggested_time = f"{next_hour - 12}:00 PM" if next_hour > 12 else "12:00 PM"
                    time_entry.insert(0, f"{suggested_time}, 2:00 PM, 8:00 PM")
                else:
                    time_entry.insert(0, "9:00 AM, 2:00 PM, 8:00 PM")
            
            time_entry.pack(side=tk.LEFT, padx=5)
            
            # Next upload preview
            preview_label = tk.Label(day_frame, text="", font=("Arial", 8), fg="green")
            preview_label.pack(side=tk.LEFT, padx=5)
            
            # For today, add background to all widgets
            if i == 0:
                time_entry.configure(bg="#FFFFFF")
                preview_label.configure(bg="#E8F4FD")
            
            # Bind update preview function
            time_entry.bind('<KeyRelease>', lambda e, d=day, te=time_entry, pl=preview_label: update_preview(d, te, pl))
            
            day_widgets[day] = {
                'enabled': enabled_var,
                'entry': time_entry,
                'preview': preview_label
            }
            
            # Initial preview update
            update_preview(day, time_entry, preview_label)
        
        # Views range
        tk.Label(scrollable_frame, text="Views Range:", font=("Arial", 10, "bold")).pack(pady=(10,5))
        views_frame = tk.Frame(scrollable_frame)
        views_frame.pack()
        
        tk.Label(views_frame, text="Min:").pack(side=tk.LEFT, padx=5)
        min_views_var = tk.IntVar(value=existing_schedule.min_views if existing_schedule else 1000)
        tk.Entry(views_frame, textvariable=min_views_var, width=10).pack(side=tk.LEFT, padx=5)
        
        tk.Label(views_frame, text="Max:").pack(side=tk.LEFT, padx=5)
        max_views_var = tk.IntVar(value=existing_schedule.max_views if existing_schedule else 10000)
        tk.Entry(views_frame, textvariable=max_views_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Duration range
        tk.Label(scrollable_frame, text="Clip Duration:", font=("Arial", 10, "bold")).pack(pady=(10,5))
        duration_var = tk.StringVar(value=existing_schedule.duration_range if existing_schedule else "15-45")
        duration_options = ["all", "0-15", "15-30", "30-60", "15-45", "custom"]
        duration_menu = ttk.Combobox(scrollable_frame, textvariable=duration_var,
                                    values=duration_options, state="readonly", width=20)
        duration_menu.pack()
        
        # Custom duration (if selected)
        custom_duration_frame = tk.Frame(scrollable_frame)
        custom_duration_frame.pack(pady=5)
        tk.Label(custom_duration_frame, text="Custom range:").pack(side=tk.LEFT, padx=5)
        custom_min_var = tk.IntVar(value=existing_schedule.custom_min_duration if existing_schedule else 15)
        tk.Entry(custom_duration_frame, textvariable=custom_min_var, width=5).pack(side=tk.LEFT, padx=2)
        tk.Label(custom_duration_frame, text="to").pack(side=tk.LEFT, padx=2)
        custom_max_var = tk.IntVar(value=existing_schedule.custom_max_duration if existing_schedule else 45)
        tk.Entry(custom_duration_frame, textvariable=custom_max_var, width=5).pack(side=tk.LEFT, padx=2)
        tk.Label(custom_duration_frame, text="seconds").pack(side=tk.LEFT, padx=2)
        
        # Days to Search Back
        tk.Label(scrollable_frame, text="Days to Search Back:", font=("Arial", 10, "bold")).pack(pady=(10,5))
        days_back_frame = tk.Frame(scrollable_frame)
        days_back_frame.pack()
        
        days_back_var = tk.IntVar(value=existing_schedule.days_back if existing_schedule else 7)
        tk.Label(days_back_frame, text="Search clips from last").pack(side=tk.LEFT, padx=5)
        tk.Spinbox(days_back_frame, from_=1, to=30, textvariable=days_back_var, 
                  width=5).pack(side=tk.LEFT, padx=5)
        tk.Label(days_back_frame, text="days").pack(side=tk.LEFT, padx=5)
        
        # Game category
        tk.Label(scrollable_frame, text="Game Category URL:", font=("Arial", 10, "bold")).pack(pady=(10,5))
        game_entry = tk.Entry(scrollable_frame, width=50)
        game_entry.insert(0, existing_schedule.game_category if existing_schedule else game_url)
        game_entry.pack()
        
        # Privacy
        tk.Label(scrollable_frame, text="Upload Privacy:", font=("Arial", 10, "bold")).pack(pady=(10,5))
        privacy_var = tk.StringVar(value=existing_schedule.privacy if existing_schedule else "private")
        privacy_menu = ttk.Combobox(scrollable_frame, textvariable=privacy_var,
                                   values=["private", "unlisted", "public"],
                                   state="readonly", width=20)
        privacy_menu.pack()
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Button frame at bottom
        button_frame = tk.Frame(schedule_window)
        button_frame.pack(side="bottom", pady=20)
        
        # Save button
        def save_schedule():
            # Validate total videos
            total_videos = landscape_count_var.get() + portrait_count_var.get()
            if total_videos == 0:
                messagebox.showerror("No Videos", 
                                   "Please select at least 1 landscape or portrait video per day!")
                return
            
            # Parse and validate weekly schedule
            has_any_schedule = False
            for day, widgets in day_widgets.items():
                if widgets['enabled'].get():
                    times_str = widgets['entry'].get()
                    upload_times = []
                    
                    if times_str.strip():  # Only process if not empty
                        for time_str in times_str.split(','):
                            time_str = time_str.strip()
                            if time_str:  # Skip empty strings
                                time_24h = convert_12h_to_24h(time_str)
                                if time_24h:
                                    upload_times.append(time_24h)
                                    has_any_schedule = True
                                else:
                                    messagebox.showerror("Invalid Time", 
                                                       f"Invalid time format for {day}: {time_str}\n\n"
                                                       "Please use 12-hour format (e.g., 9:00 AM)")
                                    return
                        
                        if len(upload_times) < total_videos:
                            messagebox.showwarning("Not Enough Times", 
                                                 f"{day}: You need at least {total_videos} upload times for {total_videos} videos per day!")
                            return
                    
                    new_schedule.weekly_schedule[day] = {
                        'enabled': widgets['enabled'].get(),
                        'times': upload_times[:total_videos]  # Only use needed times
                    }
                else:
                    new_schedule.weekly_schedule[day] = {
                        'enabled': False,
                        'times': []
                    }
            
            if not has_any_schedule:
                messagebox.showerror("No Schedule", 
                                   "Please set at least one upload time for at least one day!")
                return
            
            # Validate game URL
            game_id, game_name = self.parent.twitch_api.get_game_id(game_entry.get())
            if not game_id:
                messagebox.showerror("Invalid Game URL", 
                                   "Please enter a valid Twitch game category URL")
                return
            
            # Update schedule with form data
            new_schedule.channel_name = channel_var.get()
            new_schedule.channel_data = next((ch for ch in youtube_channels 
                                            if ch['name'] == channel_var.get()), None)
            new_schedule.landscape_videos_per_day = landscape_count_var.get()
            new_schedule.portrait_videos_per_day = portrait_count_var.get()
            new_schedule.min_views = min_views_var.get()
            new_schedule.max_views = max_views_var.get()
            new_schedule.duration_range = duration_var.get()
            new_schedule.custom_min_duration = custom_min_var.get()
            new_schedule.custom_max_duration = custom_max_var.get()
            new_schedule.game_category = game_entry.get()
            new_schedule.game_id = game_id
            new_schedule.game_name = game_name
            new_schedule.privacy = privacy_var.get()
            new_schedule.days_back = days_back_var.get()
            
            # Portrait caption settings
            new_schedule.portrait_captions_enabled = portrait_captions_var.get()
            new_schedule.portrait_caption_style = caption_style_var.get()
            new_schedule.portrait_caption_animation = caption_animation_var.get()
            new_schedule.portrait_caption_position = caption_position_var.get()
            
            # Portrait blur settings
            if blur_mode_var.get() == "custom":
                new_schedule.portrait_blur_top = blur_top_var.get()
                new_schedule.portrait_blur_bottom = blur_bottom_var.get()
            else:
                new_schedule.portrait_blur_top = 0
                new_schedule.portrait_blur_bottom = 0
            
            # Gemini settings
            new_schedule.use_gemini_titles = use_gemini_var.get()
            new_schedule.gemini_creativity = creativity_var.get()
            
            # Language filter setting
            language_name = language_var.get()
            new_schedule.language_filter = language_codes[language_name]
            
            # Handle different modes
            if edit_mode and schedule_index is not None:
                # Update existing schedule
                self.parent.automation_handler.schedules[schedule_index] = new_schedule
                self.parent.automation_handler.save_schedules()
                self.parent.refresh_automation_display()
                self.parent.automation_handler.log_func(f"✅ Updated schedule for {channel_var.get()}")
                messagebox.showinfo("Success", "Automation schedule updated successfully!")
            else:
                # Add new schedule (either brand new or duplicate)
                # Initialize tracking for new schedules
                if not hasattr(new_schedule, 'daily_upload_count') or not new_schedule.daily_upload_count:
                    new_schedule.daily_upload_count = {}
                if not hasattr(new_schedule, 'last_upload_times') or not new_schedule.last_upload_times:
                    new_schedule.last_upload_times = {}
                
                self.parent.automation_handler.add_schedule(new_schedule)
                self.parent.refresh_automation_display()
                self.parent.automation_handler.log_func(f"✅ Added schedule for {channel_var.get()}")
                
                if existing_schedule:
                    messagebox.showinfo("Success", "Automation schedule duplicated successfully!")
                else:
                    messagebox.showinfo("Success", "Automation schedule added successfully!")
            
            schedule_window.destroy()
        
        tk.Button(button_frame, text=button_text, command=save_schedule,
                 bg="green", fg="white", font=("Arial", 12), padx=20, pady=5).pack(side="left", padx=10)
        
        tk.Button(button_frame, text="Cancel", command=schedule_window.destroy).pack(side="left", padx=10)
    
    def calculate_next_upload_time(self, schedule):
        """Calculate the next upload time for a schedule"""
        try:
            now = datetime.now()
            current_day = now.strftime('%A')
            current_time = now.strftime("%H:%M")
            
            # Get days in order starting from today
            days = list(calendar.day_name)
            today_index = days.index(current_day)
            ordered_days = days[today_index:] + days[:today_index]
            
            # Find next scheduled time
            for days_ahead, day in enumerate(ordered_days):
                if day in schedule.weekly_schedule and schedule.weekly_schedule[day]['enabled']:
                    times = schedule.weekly_schedule[day]['times']
                    if times:
                        for time_str in sorted(times):
                            # If it's today, check if time hasn't passed
                            if days_ahead == 0:
                                if time_str > current_time:
                                    # Calculate hours until this time today
                                    hour, minute = map(int, time_str.split(':'))
                                    next_upload = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                    time_diff = next_upload - now
                                    hours = time_diff.total_seconds() / 3600
                                    
                                    if hours < 1:
                                        minutes = int(time_diff.total_seconds() / 60)
                                        return f"{day} at {convert_24h_to_12h(time_str)} (in {minutes} minutes)"
                                    else:
                                        return f"{day} at {convert_24h_to_12h(time_str)} (in {int(hours)} hours)"
                            else:
                                # It's a future day
                                time_12h = convert_24h_to_12h(time_str)
                                if days_ahead == 1:
                                    return f"Tomorrow at {time_12h}"
                                else:
                                    return f"{day} at {time_12h}"
            
            return "No upcoming uploads scheduled"
        except:
            return "Unable to calculate"