import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import webbrowser
from config import YOUTUBE_CREDENTIALS_DIR
from core.gemini_handler import GeminiHandler

class SettingsWindow:
    """Settings window for API keys and credentials"""
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent.root)
        self.window.title("⚙️ Settings")
        self.window.geometry("600x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_twitch_tab()
        self.create_gemini_tab()
        
        # Bottom buttons
        button_frame = tk.Frame(self.window)
        button_frame.pack(side="bottom", pady=10)
        
        tk.Button(button_frame, text="Close", command=self.window.destroy,
                 bg="gray", fg="white").pack(side="left", padx=5)
    
    def create_twitch_tab(self):
        """Create Twitch credentials tab"""
        twitch_frame = ttk.Frame(self.notebook)
        self.notebook.add(twitch_frame, text="🎮 Twitch API")
        
        # Title
        tk.Label(twitch_frame, text="Twitch API Credentials", 
                font=("Arial", 14, "bold")).pack(pady=10)
        
        # Instructions
        instructions = tk.Label(twitch_frame, 
                              text="Get your Twitch API credentials from:\nhttps://dev.twitch.tv/console/apps",
                              font=("Arial", 10), fg="blue", cursor="hand2")
        instructions.pack(pady=5)
        instructions.bind("<Button-1>", lambda e: webbrowser.open("https://dev.twitch.tv/console/apps"))
        
        # Client ID
        id_frame = tk.Frame(twitch_frame)
        id_frame.pack(pady=10, padx=20, fill="x")
        
        tk.Label(id_frame, text="Client ID:", width=15, anchor="w").pack(side="left")
        self.client_id_entry = tk.Entry(id_frame, width=50, show="")
        self.client_id_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.client_id_entry.insert(0, self.parent.twitch_api.client_id)
        
        # Client Secret
        secret_frame = tk.Frame(twitch_frame)
        secret_frame.pack(pady=10, padx=20, fill="x")
        
        tk.Label(secret_frame, text="Client Secret:", width=15, anchor="w").pack(side="left")
        self.client_secret_entry = tk.Entry(secret_frame, width=50, show="*")
        self.client_secret_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.client_secret_entry.insert(0, self.parent.twitch_api.client_secret)
        
        # Show/Hide button
        self.show_secret_var = tk.BooleanVar(value=False)
        tk.Checkbutton(secret_frame, text="Show", variable=self.show_secret_var,
                      command=self.toggle_secret_visibility).pack(side="left", padx=5)
        
        # Buttons
        button_frame = tk.Frame(twitch_frame)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="💾 Save", command=self.save_twitch_credentials,
                 bg="green", fg="white").pack(side="left", padx=5)
        
        tk.Button(button_frame, text="🧪 Test Connection", command=self.test_twitch_connection,
                 bg="blue", fg="white").pack(side="left", padx=5)
        
        # Status label
        self.twitch_status_label = tk.Label(twitch_frame, text="", font=("Arial", 10))
        self.twitch_status_label.pack(pady=10)
        
        # Help text
        help_text = tk.Label(twitch_frame, 
                           text="ℹ️ How to get credentials:\n"
                                "1. Go to Twitch Developer Console\n"
                                "2. Click 'Register Your Application'\n"
                                "3. Fill in the form (OAuth Redirect URL can be http://localhost)\n"
                                "4. Copy Client ID and Client Secret here",
                           font=("Arial", 9), fg="gray", justify="left")
        help_text.pack(pady=20)
    
    def create_gemini_tab(self):
        """Create Gemini API tab"""
        gemini_frame = ttk.Frame(self.notebook)
        self.notebook.add(gemini_frame, text="🤖 Gemini AI")
        
        # Title
        tk.Label(gemini_frame, text="Google Gemini API", 
                font=("Arial", 14, "bold")).pack(pady=10)
        
        # Check if available
        if not self.parent.gemini_handler.is_available():
            tk.Label(gemini_frame, 
                    text="⚠️ Google Generative AI not installed!\n\n"
                         "Run: pip install google-generativeai",
                    font=("Arial", 12), fg="red").pack(pady=20)
            return
        
        # Status frame
        status_frame = tk.LabelFrame(gemini_frame, text="Current Status", 
                                   font=("Arial", 10, "bold"))
        status_frame.pack(fill="x", padx=20, pady=10)
        
        self.gemini_status_display = tk.Text(status_frame, height=4, wrap=tk.WORD)
        self.gemini_status_display.pack(fill="x", padx=10, pady=5)
        
        # Update status
        self.update_gemini_status()
        
        # Refresh status button
        tk.Button(status_frame, text="🔄 Refresh Status", 
                 command=self.update_gemini_status,
                 bg="lightblue").pack(pady=5)
        
        # Instructions
        instructions = tk.Label(gemini_frame, 
                              text="Get your Gemini API key from:\nhttps://makersuite.google.com/app/apikey",
                              font=("Arial", 10), fg="blue", cursor="hand2")
        instructions.pack(pady=5)
        instructions.bind("<Button-1>", lambda e: webbrowser.open("https://makersuite.google.com/app/apikey"))
        
        # Important note about availability
        tk.Label(gemini_frame, 
                text="⚠️ Note: Gemini API may not be available in all regions.\n"
                     "If you get timeout/404 errors, the API might be restricted in your location.",
                font=("Arial", 9), fg="orange").pack(pady=5)
        
        # API Key
        key_frame = tk.Frame(gemini_frame)
        key_frame.pack(pady=10, padx=20, fill="x")
        
        tk.Label(key_frame, text="API Key:", width=15, anchor="w").pack(side="left")
        self.gemini_key_entry = tk.Entry(key_frame, width=50, show="*")
        self.gemini_key_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Load saved key
        if self.parent.gemini_handler.api_key:
            self.gemini_key_entry.insert(0, self.parent.gemini_handler.api_key)
        
        # Show/Hide button
        self.show_gemini_var = tk.BooleanVar(value=False)
        tk.Checkbutton(key_frame, text="Show", variable=self.show_gemini_var,
                      command=self.toggle_gemini_visibility).pack(side="left", padx=5)
        
        # Buttons frame
        button_frame = tk.Frame(gemini_frame)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="💾 Save", command=self.save_gemini_key,
                 bg="green", fg="white").pack(side="left", padx=5)
        
        tk.Button(button_frame, text="🧪 Test Key", command=self.test_gemini_key,
                 bg="blue", fg="white").pack(side="left", padx=5)
        
        tk.Button(button_frame, text="🔄 Reset Failures", command=self.reset_gemini_failures,
                 bg="orange", fg="white").pack(side="left", padx=5)
        
        # Status label
        self.gemini_status_label = tk.Label(gemini_frame, text="", font=("Arial", 10))
        self.gemini_status_label.pack(pady=10)
        
        # Advanced settings frame
        advanced_frame = tk.LabelFrame(gemini_frame, text="Advanced Settings", 
                                     font=("Arial", 10, "bold"))
        advanced_frame.pack(fill="x", padx=20, pady=10)
        
        # Timeout setting
        timeout_frame = tk.Frame(advanced_frame)
        timeout_frame.pack(pady=5)
        
        tk.Label(timeout_frame, text="Timeout (seconds):").pack(side="left", padx=5)
        self.timeout_var = tk.IntVar(value=self.parent.gemini_handler.timeout_seconds)
        timeout_spinbox = tk.Spinbox(timeout_frame, from_=10, to=120, 
                                   textvariable=self.timeout_var, width=10)
        timeout_spinbox.pack(side="left", padx=5)
        
        tk.Button(timeout_frame, text="Apply", 
                 command=lambda: setattr(self.parent.gemini_handler, 'timeout_seconds', self.timeout_var.get()),
                 bg="lightgray").pack(side="left", padx=5)
        
        # Info about usage
        info_text = tk.Label(gemini_frame, 
                           text="ℹ️ Gemini AI Features:\n"
                                "• Generate smart titles for videos\n"
                                "• Create engaging descriptions\n"
                                "• Optimize for YouTube SEO\n\n"
                                "For Shorts: 2-3 word titles + game hashtag + #gaming\n"
                                "For Regular videos: Full optimized titles and descriptions\n\n"
                                "Using model: gemini-1.5-flash (fast & efficient)\n\n"
                                "⚠️ Automation Protection:\n"
                                "• 45 second timeout for automation\n"
                                "• 3 retries with exponential backoff\n"
                                "• Auto-bypass after 3 consecutive failures\n"
                                "• Falls back to default titles if needed\n\n"
                                "💡 Troubleshooting:\n"
                                "• If you get timeout errors, try increasing timeout\n"
                                "• If stuck, click 'Reset Failures' button\n"
                                "• Some regions may have API restrictions\n"
                                "• The tool works perfectly without Gemini too!",
                           font=("Arial", 9), fg="gray", justify="left")
        info_text.pack(pady=20)
    
    def update_gemini_status(self):
        """Update Gemini status display"""
        try:
            status = self.parent.gemini_handler.get_status()
            
            status_text = ""
            if status['available']:
                status_text += "✅ Gemini library: Available\n"
            else:
                status_text += "❌ Gemini library: Not installed\n"
            
            if status['api_key_set']:
                status_text += "✅ API Key: Set\n"
            else:
                status_text += "❌ API Key: Not set\n"
            
            if status['initialized']:
                status_text += "✅ Model: Initialized\n"
            else:
                status_text += "❌ Model: Not initialized\n"
            
            if status['bypassed']:
                status_text += f"⚠️ Status: Bypassed ({status['consecutive_failures']} failures)\n"
            elif status['consecutive_failures'] > 0:
                status_text += f"⚠️ Consecutive failures: {status['consecutive_failures']}\n"
            else:
                status_text += "✅ Status: Working normally\n"
            
            if status['last_error']:
                status_text += f"Last error: {status['last_error'][:50]}...\n"
            
            status_text += f"Cache size: {status['cache_size']} titles"
            
            self.gemini_status_display.delete(1.0, tk.END)
            self.gemini_status_display.insert(1.0, status_text)
            
        except Exception as e:
            self.gemini_status_display.delete(1.0, tk.END)
            self.gemini_status_display.insert(1.0, f"Error getting status: {str(e)}")
    
    def reset_gemini_failures(self):
        """Reset Gemini consecutive failures"""
        try:
            self.parent.gemini_handler.reset_failure_counter()
            self.update_gemini_status()
            self.gemini_status_label.config(text="✅ Failure counter reset!", fg="green")
            messagebox.showinfo("Reset Complete", "Gemini failure counter has been reset.\n\nAutomation will now attempt to use Gemini AI again.")
        except Exception as e:
            self.gemini_status_label.config(text=f"❌ Error resetting: {str(e)}", fg="red")
    
    def toggle_secret_visibility(self):
        """Toggle visibility of client secret"""
        if self.show_secret_var.get():
            self.client_secret_entry.config(show="")
        else:
            self.client_secret_entry.config(show="*")
    
    def toggle_gemini_visibility(self):
        """Toggle visibility of Gemini key"""
        if self.show_gemini_var.get():
            self.gemini_key_entry.config(show="")
        else:
            self.gemini_key_entry.config(show="*")
    
    def save_twitch_credentials(self):
        """Save Twitch credentials"""
        client_id = self.client_id_entry.get().strip()
        client_secret = self.client_secret_entry.get().strip()
        
        if not client_id or not client_secret:
            messagebox.showerror("Error", "Please enter both Client ID and Client Secret!")
            return
        
        # Save to parent
        self.parent.twitch_api.client_id = client_id
        self.parent.twitch_api.client_secret = client_secret
        
        # Save to file
        creds_file = os.path.join(YOUTUBE_CREDENTIALS_DIR, "twitch_credentials.json")
        try:
            with open(creds_file, 'w') as f:
                json.dump({
                    'client_id': client_id,
                    'client_secret': client_secret
                }, f)
            
            self.twitch_status_label.config(text="✅ Credentials saved successfully!", fg="green")
            self.parent.log("✅ Twitch credentials saved")
            
            # Re-authenticate
            success, message = self.parent.twitch_api.authenticate()
            if success:
                self.parent.log(f"✅ {message}")
            else:
                self.parent.log(f"❌ {message}")
            
        except Exception as e:
            self.twitch_status_label.config(text=f"❌ Error saving: {str(e)}", fg="red")
    
    def test_twitch_connection(self):
        """Test Twitch API connection"""
        import requests
        
        self.twitch_status_label.config(text="Testing connection...", fg="blue")
        self.window.update()
        
        client_id = self.client_id_entry.get().strip()
        client_secret = self.client_secret_entry.get().strip()
        
        if not client_id or not client_secret:
            self.twitch_status_label.config(text="❌ Please enter credentials first!", fg="red")
            return
        
        try:
            # Try to authenticate
            auth_url = "https://id.twitch.tv/oauth2/token"
            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'client_credentials'
            }
            
            response = requests.post(auth_url, data=data, timeout=10)
            if response.status_code == 200:
                self.twitch_status_label.config(text="✅ Connection successful!", fg="green")
                messagebox.showinfo("Success", "Twitch API connection successful!")
            else:
                self.twitch_status_label.config(text="❌ Invalid credentials!", fg="red")
                messagebox.showerror("Error", "Invalid credentials!\n\nPlease check your Client ID and Secret.")
                
        except requests.exceptions.Timeout:
            self.twitch_status_label.config(text="❌ Connection timeout!", fg="red")
            messagebox.showerror("Error", "Connection timeout! Check your internet connection.")
        except Exception as e:
            self.twitch_status_label.config(text=f"❌ Error: {str(e)}", fg="red")
            messagebox.showerror("Error", f"Connection failed:\n{str(e)}")
    
    def save_gemini_key(self):
        """Save Gemini API key"""
        api_key = self.gemini_key_entry.get().strip()
        
        if not api_key:
            messagebox.showerror("Error", "Please enter an API key!")
            return
        
        # Save to parent
        self.parent.gemini_handler.api_key = api_key
        
        # Save to file
        creds_file = os.path.join(YOUTUBE_CREDENTIALS_DIR, "gemini_key.json")
        try:
            with open(creds_file, 'w') as f:
                json.dump({'api_key': api_key}, f)
            
            self.gemini_status_label.config(text="✅ API key saved successfully!", fg="green")
            self.parent.log("✅ Gemini API key saved")
            
            # Initialize Gemini
            self.parent.gemini_handler.initialize(api_key, self.parent.log)
            
        except Exception as e:
            self.gemini_status_label.config(text=f"❌ Error saving: {str(e)}", fg="red")
    
    def test_gemini_key(self):
        """Test Gemini API key"""
        self.gemini_status_label.config(text="Testing API key...", fg="blue")
        self.window.update()
        
        api_key = self.gemini_key_entry.get().strip()
        
        if not api_key:
            self.gemini_status_label.config(text="❌ Please enter an API key first!", fg="red")
            return
        
        # Create temporary handler for testing
        test_handler = GeminiHandler()
        success, result = test_handler.test_api_key(api_key)
        
        if success:
            self.gemini_status_label.config(text="✅ API key is valid!", fg="green")
            messagebox.showinfo("Success", f"Gemini API is working!\n\nResponse: {result}...")
        else:
            self.gemini_status_label.config(text=f"❌ {result.split('.')[0]}...", fg="red")
            messagebox.showerror("Error", result)