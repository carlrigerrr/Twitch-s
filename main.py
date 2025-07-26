#!/usr/bin/env python3
"""
Twitch Clip Downloader with YouTube Upload & Automation
Main entry point for the application
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from ui.main_window import TwitchClipDownloader

def main():
    """Main function to start the application"""
    print("Starting Twitch Clip Downloader...")
    print("Required modules: tkinter, requests, moviepy, whisper, openpyxl, google-api-python-client, google-generativeai")
    print("Make sure FFmpeg is installed on your system!")
    print()
    
    # Create the main window
    root = tk.Tk()
    
    # Create the application
    app = TwitchClipDownloader(root)
    
    # Start the main loop
    root.mainloop()

if __name__ == "__main__":
    main()