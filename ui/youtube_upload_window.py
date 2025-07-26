import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import threading
from datetime import datetime, timedelta

class YouTubeUploadWindow:
    """Window for selecting videos to upload to YouTube"""
    def __init__(self, parent, videos, channels, game_name):
        self.parent = parent
        self.videos = videos  # List of video file paths
        self.channels = channels  # List of authenticated channels
        self.game_name = game_name
        self.upload_tasks = []
        
        # Create window
        self.window = tk.Toplevel(parent.root)
        self.window.title("📺 Upload Videos to YouTube")
        self.window.geometry("900x700")
        
        # Make window modal
        self.window.transient(parent.root)
        self.window.grab_set()
        
        self.setup_ui()
        
    def setup_ui(self):
        """Build the upload selection UI"""
        # Title
        title = tk.Label(self.window, text="Select Videos to Upload to YouTube", 
                        font=("Arial", 16, "bold"))
        title.pack(pady=10)
        
        # Main frame with scrollbar
        main_frame = tk.Frame(self.window)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Create canvas and scrollbar for video list
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Video selection
        self.video_vars = []
        self.channel_vars = []
        self.title_entries = []
        self.desc_entries = []
        self.privacy_vars = []
        self.schedule_vars = []
        self.schedule_entries = []
        
        for i, video_path in enumerate(self.videos):
            # Frame for each video
            video_frame = tk.LabelFrame(scrollable_frame, text=f"Video {i+1}", 
                                      font=("Arial", 10, "bold"), padx=10, pady=5)
            video_frame.grid(row=i, column=0, sticky="ew", padx=5, pady=5)
            
            # Checkbox to select video
            var = tk.BooleanVar(value=True)
            self.video_vars.append(var)
            
            filename = os.path.basename(video_path)
            check = tk.Checkbutton(video_frame, text=filename[:50] + "...", 
                                 variable=var, font=("Arial", 9))
            check.grid(row=0, column=0, columnspan=3, sticky="w", pady=5)
            
            # Channel selection
            tk.Label(video_frame, text="Channel:").grid(row=1, column=0, sticky="w", padx=(20, 5))
            channel_var = tk.StringVar(value=self.channels[0]['name'] if self.channels else "")
            self.channel_vars.append(channel_var)
            
            channel_menu = ttk.Combobox(video_frame, textvariable=channel_var,
                                       values=[ch['name'] for ch in self.channels],
                                       state="readonly", width=25)
            channel_menu.grid(row=1, column=1, sticky="w", padx=5)
            
            # Privacy setting
            tk.Label(video_frame, text="Privacy:").grid(row=1, column=2, sticky="w", padx=5)
            privacy_var = tk.StringVar(value="private")
            self.privacy_vars.append(privacy_var)
            
            privacy_menu = ttk.Combobox(video_frame, textvariable=privacy_var,
                                      values=["private", "unlisted", "public"],
                                      state="readonly", width=10)
            privacy_menu.grid(row=1, column=3, sticky="w", padx=5)
            
            # Title
            tk.Label(video_frame, text="Title:").grid(row=2, column=0, sticky="w", padx=(20, 5))
            
            # Auto-generate title from filename
            clean_title = self.generate_title_from_filename(filename)
            title_entry = tk.Entry(video_frame, width=60)
            title_entry.insert(0, clean_title)
            title_entry.grid(row=2, column=1, columnspan=3, sticky="w", padx=5, pady=2)
            self.title_entries.append(title_entry)
            
            # Description
            tk.Label(video_frame, text="Description:").grid(row=3, column=0, sticky="nw", padx=(20, 5))
            
            desc_frame = tk.Frame(video_frame)
            desc_frame.grid(row=3, column=1, columnspan=3, sticky="w", padx=5, pady=2)
            
            desc_entry = tk.Text(desc_frame, width=60, height=3, wrap=tk.WORD)
            desc_scrollbar = ttk.Scrollbar(desc_frame, command=desc_entry.yview)
            desc_entry.configure(yscrollcommand=desc_scrollbar.set)
            
            # Auto-generate description
            desc_text = f"Gaming clip from {self.game_name}"
            desc_entry.insert("1.0", desc_text)
            
            desc_entry.pack(side="left")
            desc_scrollbar.pack(side="right", fill="y")
            self.desc_entries.append(desc_entry)
            
            # Schedule option
            schedule_frame = tk.Frame(video_frame)
            schedule_frame.grid(row=4, column=0, columnspan=4, sticky="w", padx=(20, 5), pady=5)
            
            schedule_var = tk.BooleanVar(value=False)
            self.schedule_vars.append(schedule_var)
            
            schedule_check = tk.Checkbutton(schedule_frame, text="Schedule for later:",
                                          variable=schedule_var,
                                          command=lambda idx=i: self.toggle_schedule(idx))
            schedule_check.pack(side="left")
            
            schedule_entry = tk.Entry(schedule_frame, width=20, state="disabled")
            schedule_entry.insert(0, (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
            schedule_entry.pack(side="left", padx=5)
            self.schedule_entries.append(schedule_entry)
            
            tk.Label(schedule_frame, text="(YYYY-MM-DD HH:MM)", 
                    font=("Arial", 8), fg="gray").pack(side="left", padx=5)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Buttons frame
        button_frame = tk.Frame(self.window)
        button_frame.pack(pady=10)
        
        # Select all/none buttons
        tk.Button(button_frame, text="Select All", 
                 command=self.select_all).pack(side="left", padx=5)
        tk.Button(button_frame, text="Select None", 
                 command=self.select_none).pack(side="left", padx=5)
        
        # Upload button
        upload_btn = tk.Button(button_frame, text="🚀 Upload Selected Videos", 
                             command=self.start_upload,
                             bg="red", fg="white", font=("Arial", 12, "bold"),
                             padx=20, pady=5)
        upload_btn.pack(side="left", padx=20)
        
        # Cancel button
        tk.Button(button_frame, text="Cancel", 
                 command=self.window.destroy).pack(side="left", padx=5)
        
        # Progress area
        self.progress_frame = tk.Frame(self.window)
        self.progress_frame.pack(fill="x", padx=20, pady=10)
        
        self.progress_label = tk.Label(self.progress_frame, text="", fg="blue")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, length=400, mode='determinate')
        self.progress_bar.pack(pady=5)
    
    def generate_title_from_filename(self, filename):
        """Generate a clean title from filename"""
        # Remove extension
        title = os.path.splitext(filename)[0]
        # Remove number prefix and clip ID suffix
        title = re.sub(r'^\d+_', '', title)  # Remove number prefix
        title = re.sub(r'_[a-zA-Z0-9\-]+_portrait$', '', title)  # Remove clip ID and portrait
        title = re.sub(r'_[a-zA-Z0-9\-]+$', '', title)  # Remove clip ID
        # Replace underscores with spaces
        title = title.replace('_', ' ')
        # Add game name
        title = f"{title} - {self.game_name} Gameplay"
        return title[:100]  # YouTube title limit
    
    def toggle_schedule(self, idx):
        """Enable/disable schedule entry based on checkbox"""
        if self.schedule_vars[idx].get():
            self.schedule_entries[idx].config(state="normal")
        else:
            self.schedule_entries[idx].config(state="disabled")
    
    def select_all(self):
        """Select all videos"""
        for var in self.video_vars:
            var.set(True)
    
    def select_none(self):
        """Deselect all videos"""
        for var in self.video_vars:
            var.set(False)
    
    def start_upload(self):
        """Start uploading selected videos"""
        # Collect upload tasks
        self.upload_tasks = []
        
        for i, selected in enumerate(self.video_vars):
            if selected.get():
                task = {
                    'video_path': self.videos[i],
                    'channel': next((ch for ch in self.channels if ch['name'] == self.channel_vars[i].get()), None),
                    'title': self.title_entries[i].get(),
                    'description': self.desc_entries[i].get("1.0", "end-1c"),
                    'privacy': self.privacy_vars[i].get(),
                    'scheduled': self.schedule_vars[i].get(),
                    'schedule_time': self.schedule_entries[i].get() if self.schedule_vars[i].get() else None
                }
                
                if task['channel']:
                    self.upload_tasks.append(task)
        
        if not self.upload_tasks:
            messagebox.showwarning("No Videos Selected", "Please select at least one video to upload!")
            return
        
        # Disable UI during upload
        for child in self.window.winfo_children():
            if isinstance(child, (tk.Button, ttk.Button)):
                child.config(state='disabled')
        
        # Start upload in thread
        thread = threading.Thread(target=self.upload_process)
        thread.daemon = True
        thread.start()
    
    def upload_process(self):
        """Upload videos to YouTube"""
        try:
            self.progress_bar['maximum'] = len(self.upload_tasks)
            successful = 0
            
            for i, task in enumerate(self.upload_tasks):
                self.progress_label.config(text=f"Uploading {i+1}/{len(self.upload_tasks)}: {os.path.basename(task['video_path'])}")
                
                try:
                    # Upload video
                    video_id = self.parent.youtube_handler.upload_video(
                        task['channel'],
                        task['video_path'],
                        task['title'],
                        task['description'],
                        task['privacy'],
                        task['scheduled'],
                        task['schedule_time'],
                        tags=['gaming', 'twitch', 'clips', self.game_name],
                        log_func=self.parent.log
                    )
                    
                    if video_id:
                        successful += 1
                        self.parent.log(f"✅ Uploaded: {task['title']}")
                    else:
                        self.parent.log(f"❌ Failed to upload: {task['title']}")
                        
                except Exception as e:
                    self.parent.log(f"❌ Upload error: {str(e)}")
                
                self.progress_bar['value'] = i + 1
                self.window.update_idletasks()
            
            # Show results
            self.progress_label.config(text=f"Upload complete! {successful}/{len(self.upload_tasks)} videos uploaded successfully", fg="green")
            
            messagebox.showinfo("Upload Complete", 
                              f"Successfully uploaded {successful} out of {len(self.upload_tasks)} videos!")
            
            # Close window after delay
            self.window.after(2000, self.window.destroy)
            
        except Exception as e:
            self.progress_label.config(text=f"Error: {str(e)}", fg="red")
            messagebox.showerror("Upload Error", f"An error occurred:\n{str(e)}")