import json
import os
import time
import queue
import threading
import uuid
import shutil
from datetime import datetime, timedelta
import calendar
from config import AUTOMATION_FILE, AUTOMATION_CHECK_INTERVAL, AUTOMATION_RETRY_DELAY, AUTOMATION_MAX_RETRIES
from utils.helpers import check_internet_connection

class AutomationSchedule:
    """Class to hold automation schedule data"""
    def __init__(self):
        self.channel_name = ""
        self.channel_data = None
        self.landscape_videos_per_day = 0
        self.portrait_videos_per_day = 0
        self.weekly_schedule = {
            'Monday': {'enabled': True, 'times': []},
            'Tuesday': {'enabled': True, 'times': []},
            'Wednesday': {'enabled': True, 'times': []},
            'Thursday': {'enabled': True, 'times': []},
            'Friday': {'enabled': True, 'times': []},
            'Saturday': {'enabled': True, 'times': []},
            'Sunday': {'enabled': True, 'times': []}
        }
        self.min_views = 100
        self.max_views = 5000
        self.duration_range = "all"
        self.custom_min_duration = 10
        self.custom_max_duration = 30
        self.game_category = ""
        self.game_id = ""
        self.game_name = ""
        self.privacy = "private"
        self.enabled = True
        self.daily_upload_count = {}
        self.portrait_captions_enabled = True
        self.portrait_caption_style = "modern"
        self.portrait_caption_animation = "pop"
        self.portrait_caption_position = "center"
        self.last_upload_times = {}
        self.last_check_time = None
        self.days_back = 7
        self.portrait_blur_top = 0
        self.portrait_blur_bottom = 0
        self.use_gemini_titles = False
        self.gemini_creativity = "balanced"
        # NEW: Language filter settings
        self.language_filter = "all"  # Language code for filtering clips

class AutomationHandler:
    def __init__(self, log_func=None, show_notification_func=None):
        self.schedules = []
        self.enabled = False
        self.queue = queue.Queue()
        self.stop_flag = False
        self.scheduler_thread = None
        self.worker_thread = None  # NEW: Single worker thread for sequential processing
        self.log_func = log_func
        self.show_notification_func = show_notification_func
        self.last_error = None
        self.error_count = 0
        
        # NEW: Sequential processing tracking
        self.current_task = None
        self.queue_lock = threading.Lock()
        self.processing_lock = threading.Lock()  # Ensure only one task processes at a time
        
        # NEW: Task tracking for better status reporting
        self.total_tasks_processed = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.last_task_time = None
        
        # Cleanup tracking
        self.temp_folders = set()
        self.cleanup_lock = threading.Lock()
        
    def save_schedules(self):
        """Save automation schedules to file"""
        schedules_data = []
        for schedule in self.schedules:
            # Ensure required attributes exist
            if not hasattr(schedule, 'daily_upload_count'):
                schedule.daily_upload_count = {}
            if not hasattr(schedule, 'last_upload_times'):
                schedule.last_upload_times = {}
            if not hasattr(schedule, 'days_back'):
                schedule.days_back = 7
            if not hasattr(schedule, 'portrait_blur_top'):
                schedule.portrait_blur_top = 0
            if not hasattr(schedule, 'portrait_blur_bottom'):
                schedule.portrait_blur_bottom = 0
            if not hasattr(schedule, 'use_gemini_titles'):
                schedule.use_gemini_titles = False
            if not hasattr(schedule, 'gemini_creativity'):
                schedule.gemini_creativity = "balanced"
            if not hasattr(schedule, 'language_filter'):
                schedule.language_filter = "all"
                
            data = {
                'channel_name': schedule.channel_name,
                'landscape_videos_per_day': schedule.landscape_videos_per_day,
                'portrait_videos_per_day': schedule.portrait_videos_per_day,
                'weekly_schedule': schedule.weekly_schedule,
                'min_views': schedule.min_views,
                'max_views': schedule.max_views,
                'duration_range': schedule.duration_range,
                'custom_min_duration': schedule.custom_min_duration,
                'custom_max_duration': schedule.custom_max_duration,
                'game_category': schedule.game_category,
                'game_id': schedule.game_id,
                'game_name': schedule.game_name,
                'privacy': schedule.privacy,
                'enabled': schedule.enabled,
                'daily_upload_count': schedule.daily_upload_count,
                'last_upload_times': schedule.last_upload_times,
                'days_back': schedule.days_back,
                'portrait_captions_enabled': schedule.portrait_captions_enabled,
                'portrait_caption_style': schedule.portrait_caption_style,
                'portrait_caption_animation': schedule.portrait_caption_animation,
                'portrait_caption_position': schedule.portrait_caption_position,
                'portrait_blur_top': schedule.portrait_blur_top,
                'portrait_blur_bottom': schedule.portrait_blur_bottom,
                'use_gemini_titles': schedule.use_gemini_titles,
                'gemini_creativity': schedule.gemini_creativity,
                'language_filter': schedule.language_filter  # NEW: Save language filter
            }
            schedules_data.append(data)
        
        try:
            with open(AUTOMATION_FILE, 'w', encoding='utf-8') as f:
                json.dump(schedules_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            if self.log_func:
                self.log_func(f"⚠️ Error saving schedules: {str(e)}")
    
    def load_schedules(self, youtube_channels):
        """Load automation schedules from file"""
        if os.path.exists(AUTOMATION_FILE):
            try:
                with open(AUTOMATION_FILE, 'r', encoding='utf-8') as f:
                    schedules_data = json.load(f)
                
                self.schedules = []
                for data in schedules_data:
                    schedule = AutomationSchedule()
                    
                    # Load all attributes
                    for key, value in data.items():
                        if hasattr(schedule, key):
                            setattr(schedule, key, value)
                    
                    # Handle old format conversion
                    if 'weekly_schedule' not in data and 'upload_times' in data:
                        # Convert old daily schedule to weekly
                        times = data['upload_times']
                        for day in calendar.day_name:
                            schedule.weekly_schedule[day] = {
                                'enabled': True,
                                'times': times
                            }
                    
                    # NEW: Ensure language_filter exists
                    if not hasattr(schedule, 'language_filter'):
                        schedule.language_filter = "all"
                    
                    # Find matching channel
                    schedule.channel_data = next((ch for ch in youtube_channels 
                                                if ch['name'] == schedule.channel_name), None)
                    
                    if schedule.channel_data:
                        self.schedules.append(schedule)
                    else:
                        if self.log_func:
                            self.log_func(f"⚠️ Channel '{schedule.channel_name}' not found, removing schedule")
                
            except Exception as e:
                if self.log_func:
                    self.log_func(f"⚠️ Error loading schedules: {str(e)}")
    
    def start_scheduler(self):
        """Start the automation scheduler and worker threads"""
        self.stop_flag = False
        
        # Start scheduler thread (checks for new tasks)
        self.scheduler_thread = threading.Thread(target=self.scheduler_worker, name="AutomationScheduler")
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        # Start sequential worker thread (processes tasks one by one)
        self.worker_thread = threading.Thread(target=self.sequential_worker, name="AutomationWorker")
        self.worker_thread.daemon = True
        self.worker_thread.start()
        
        if self.log_func:
            self.log_func("🚀 Automation scheduler and sequential worker started")
    
    def stop_scheduler(self):
        """Stop the automation scheduler and worker"""
        self.stop_flag = True
        
        # Stop both threads
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=2)
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)  # Give worker more time to finish current task
        
        # Clean up any remaining temp folders
        self.cleanup_all_temp_folders()
        
        if self.log_func:
            self.log_func("🛑 Automation scheduler and worker stopped")
    
    def cleanup_all_temp_folders(self):
        """Clean up all temporary folders"""
        with self.cleanup_lock:
            for temp_folder in list(self.temp_folders):
                try:
                    if os.path.exists(temp_folder):
                        shutil.rmtree(temp_folder, ignore_errors=True)
                        if self.log_func:
                            self.log_func(f"🧹 Cleaned up temp folder: {os.path.basename(temp_folder)}")
                except Exception as e:
                    if self.log_func:
                        self.log_func(f"⚠️ Error cleaning temp folder: {str(e)}")
            self.temp_folders.clear()
    
    def register_temp_folder(self, temp_folder):
        """Register a temp folder for cleanup"""
        with self.cleanup_lock:
            self.temp_folders.add(temp_folder)
    
    def unregister_temp_folder(self, temp_folder):
        """Unregister and clean up a temp folder"""
        with self.cleanup_lock:
            try:
                if os.path.exists(temp_folder):
                    shutil.rmtree(temp_folder, ignore_errors=True)
                self.temp_folders.discard(temp_folder)
            except Exception as e:
                if self.log_func:
                    self.log_func(f"⚠️ Error cleaning temp folder: {str(e)}")
    
    def scheduler_worker(self):
        """Background scheduler that checks for new tasks to add to queue"""
        if self.log_func:
            self.log_func("🔍 Automation scheduler started (checking every 10 seconds)")
        
        retry_count = 0
        last_internet_check = 0
        
        while not self.stop_flag:
            try:
                current_time = time.time()
                
                # Check internet connection every 60 seconds
                if current_time - last_internet_check > 60:
                    if not check_internet_connection():
                        if self.log_func:
                            self.log_func("⚠️ No internet connection. Waiting 60 seconds...")
                        if self.show_notification_func:
                            self.show_notification_func("⚠️ No Internet Connection", "orange")
                        time.sleep(60)
                        continue
                    last_internet_check = current_time
                
                if self.enabled:
                    now = datetime.now()
                    current_time_str = now.strftime("%H:%M")
                    current_day = now.strftime("%A")
                    today_str = now.strftime("%Y-%m-%d")
                    
                    # Check each schedule
                    for schedule in self.schedules:
                        if self.stop_flag:
                            break
                            
                        if schedule.enabled and schedule.channel_data:
                            try:
                                # Check if this day is enabled
                                if current_day in schedule.weekly_schedule:
                                    day_config = schedule.weekly_schedule[current_day]
                                    if day_config['enabled'] and day_config['times']:
                                        # Initialize daily count if needed
                                        if today_str not in schedule.daily_upload_count:
                                            schedule.daily_upload_count[today_str] = {
                                                'landscape': 0,
                                                'portrait': 0
                                            }
                                            # Clean old daily counts
                                            self.clean_old_daily_counts(schedule)
                                        
                                        # Get current counts
                                        counts = schedule.daily_upload_count[today_str]
                                        landscape_done = counts.get('landscape', 0)
                                        portrait_done = counts.get('portrait', 0)
                                        
                                        # Check if current time matches any upload time
                                        if current_time_str in day_config['times']:
                                            # Create unique key for this time slot
                                            time_key = f"{current_day}_{today_str}_{current_time_str}"
                                            
                                            # Check if we haven't already processed this time slot
                                            if schedule.last_upload_times.get(f"{current_day}_{current_time_str}") != time_key:
                                                # Determine what videos need to be uploaded
                                                tasks_to_add = []
                                                
                                                # Add landscape tasks
                                                if landscape_done < schedule.landscape_videos_per_day:
                                                    for i in range(schedule.landscape_videos_per_day - landscape_done):
                                                        task_data = {
                                                            'type': 'upload',
                                                            'schedule': schedule,
                                                            'format_type': 'landscape',
                                                            'trigger_time': now.strftime("%H:%M:%S"),
                                                            'day': current_day,
                                                            'unique_id': str(uuid.uuid4()),
                                                            'task_number': i + 1,
                                                            'priority': 1  # Lower number = higher priority
                                                        }
                                                        tasks_to_add.append(task_data)
                                                
                                                # Add portrait tasks
                                                if portrait_done < schedule.portrait_videos_per_day:
                                                    for i in range(schedule.portrait_videos_per_day - portrait_done):
                                                        task_data = {
                                                            'type': 'upload',
                                                            'schedule': schedule,
                                                            'format_type': 'portrait',
                                                            'trigger_time': now.strftime("%H:%M:%S"),
                                                            'day': current_day,
                                                            'unique_id': str(uuid.uuid4()),
                                                            'task_number': i + 1,
                                                            'priority': 2  # Portraits after landscapes
                                                        }
                                                        tasks_to_add.append(task_data)
                                                
                                                # Add all tasks to queue
                                                if tasks_to_add:
                                                    with self.queue_lock:
                                                        for task_data in tasks_to_add:
                                                            try:
                                                                self.queue.put(task_data, timeout=5)
                                                                if self.log_func:
                                                                    self.log_func(f"⏰ Queued {task_data['format_type']} task for {schedule.channel_name}")
                                                            except queue.Full:
                                                                if self.log_func:
                                                                    self.log_func(f"⚠️ Queue full! Skipping task for {schedule.channel_name}")
                                                    
                                                    # Show notification for triggered automation
                                                    total_tasks = len(tasks_to_add)
                                                    if self.show_notification_func:
                                                        self.show_notification_func(
                                                            f"🎬 AUTOMATION TRIGGERED: {schedule.channel_name} - {total_tasks} videos queued",
                                                            "blue"
                                                        )
                                                    
                                                    if self.log_func:
                                                        self.log_func(f"✅ Added {total_tasks} tasks to queue for {schedule.channel_name}")
                                                
                                                # Mark time slot as processed
                                                schedule.last_upload_times[f"{current_day}_{current_time_str}"] = time_key
                                                
                                                # Save schedules after updating
                                                self.save_schedules()
                                                
                            except Exception as schedule_error:
                                if self.log_func:
                                    self.log_func(f"❌ Error checking schedule for {schedule.channel_name}: {str(schedule_error)}")
                                if self.show_notification_func:
                                    self.show_notification_func(f"❌ SCHEDULE ERROR: {schedule.channel_name}", "red")
                
                # Reset retry count on successful loop
                retry_count = 0
                self.error_count = 0
                self.last_error = None
                
                # Check every interval seconds
                time.sleep(AUTOMATION_CHECK_INTERVAL)
                
            except Exception as e:
                retry_count += 1
                self.error_count += 1
                self.last_error = str(e)
                
                if self.log_func:
                    self.log_func(f"❌ Scheduler error (attempt {retry_count}/{AUTOMATION_MAX_RETRIES}): {str(e)}")
                
                if self.show_notification_func:
                    self.show_notification_func(f"❌ SCHEDULER ERROR: {str(e)[:50]}...", "red")
                
                if retry_count >= AUTOMATION_MAX_RETRIES:
                    if self.log_func:
                        self.log_func("⚠️ Too many scheduler errors. Pausing for 5 minutes...")
                    if self.show_notification_func:
                        self.show_notification_func("⚠️ SCHEDULER PAUSED: Too many errors", "red")
                    time.sleep(300)  # Wait 5 minutes before retrying
                    retry_count = 0
                else:
                    time.sleep(AUTOMATION_RETRY_DELAY)
        
        if self.log_func:
            self.log_func("🛑 Automation scheduler stopped")
    
    def sequential_worker(self):
        """NEW: Sequential worker that processes one task at a time"""
        if self.log_func:
            self.log_func("🔄 Sequential automation worker started")
        
        while not self.stop_flag:
            try:
                # Get next task from queue (blocking with timeout)
                try:
                    task_data = self.queue.get(timeout=5)  # Wait 5 seconds for new task
                except queue.Empty:
                    continue  # No tasks, continue checking
                
                if not task_data or self.stop_flag:
                    continue
                
                # Process the task (ONE AT A TIME)
                with self.processing_lock:  # Ensure only one task processes at a time
                    self.current_task = task_data
                    self.process_single_task(task_data)
                    self.current_task = None
                    
                    # Mark task as done
                    self.queue.task_done()
                    
                    # Update statistics
                    self.total_tasks_processed += 1
                    self.last_task_time = datetime.now()
                    
                    # Small delay between tasks to prevent overwhelming
                    if not self.stop_flag:
                        time.sleep(2)  # 2 second delay between tasks
                
            except Exception as e:
                if self.log_func:
                    self.log_func(f"❌ Sequential worker error: {str(e)}")
                time.sleep(5)  # Wait before continuing
        
        if self.log_func:
            self.log_func("🛑 Sequential automation worker stopped")
    
    def process_single_task(self, task_data):
        """Process a single automation task (called by sequential worker)"""
        # This method will be implemented in the main_window.py file
        # as it needs access to the main application components
        pass
    
    def clean_old_daily_counts(self, schedule):
        """Remove daily counts older than 7 days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=7)
            old_dates = []
            
            for date_str in schedule.daily_upload_count:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    if date_obj < cutoff_date:
                        old_dates.append(date_str)
                except:
                    pass
            
            for date_str in old_dates:
                del schedule.daily_upload_count[date_str]
            
            if old_dates:
                self.save_schedules()
        except:
            pass
    
    def add_schedule(self, schedule):
        """Add a new schedule"""
        self.schedules.append(schedule)
        self.save_schedules()
        if self.log_func:
            self.log_func(f"✅ Added schedule for {schedule.channel_name}")
    
    def remove_schedule(self, index):
        """Remove a schedule"""
        if 0 <= index < len(self.schedules):
            removed_schedule = self.schedules.pop(index)
            self.save_schedules()
            if self.log_func:
                self.log_func(f"❌ Removed schedule for {removed_schedule.channel_name}")
    
    def toggle_schedule(self, index):
        """Toggle a schedule on/off"""
        if 0 <= index < len(self.schedules):
            self.schedules[index].enabled = not self.schedules[index].enabled
            self.save_schedules()
            status = "enabled" if self.schedules[index].enabled else "disabled"
            if self.log_func:
                self.log_func(f"🔄 Schedule {index+1} {status}")
    
    def get_queue_size(self):
        """Get current queue size"""
        with self.queue_lock:
            return self.queue.qsize()
    
    def get_status_info(self):
        """Get detailed status information"""
        return {
            'enabled': self.enabled,
            'scheduler_alive': self.scheduler_thread.is_alive() if self.scheduler_thread else False,
            'worker_alive': self.worker_thread.is_alive() if self.worker_thread else False,
            'queue_size': self.get_queue_size(),
            'schedules_count': len(self.schedules),
            'current_task': self.current_task,
            'total_processed': self.total_tasks_processed,
            'successful_tasks': self.successful_tasks,
            'failed_tasks': self.failed_tasks,
            'last_task_time': self.last_task_time,
            'last_error': self.last_error,
            'error_count': self.error_count
        }