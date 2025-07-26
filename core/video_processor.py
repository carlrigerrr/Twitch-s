import os
import subprocess
import shutil
import time
import uuid
import gc
import sys
from config import KARAOKE_COLORS, DEFAULT_FONT_SIZE_DIVISOR, STROKE_WIDTH_DIVISOR

# Try to import required libraries
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

try:
    from moviepy.editor import *
    from moviepy.video.tools.subtitles import SubtitlesClip
    from moviepy.video.fx.resize import resize
    from moviepy.config import change_settings
    import numpy as np
    MOVIEPY_AVAILABLE = True
    
    # Fix for Pillow 10.0.0+
    try:
        from PIL import Image
        if not hasattr(Image, 'ANTIALIAS'):
            Image.ANTIALIAS = Image.LANCZOS
    except ImportError:
        pass
    
    # Configure ImageMagick for MoviePy (Windows)
    if os.name == 'nt':
        imagemagick_paths = [
            r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
            r"C:\Program Files\ImageMagick-7.1.0-Q16\magick.exe",
            r"C:\Program Files (x86)\ImageMagick\magick.exe",
            r"C:\ImageMagick\magick.exe"
        ]
        
        for path in imagemagick_paths:
            if os.path.exists(path):
                change_settings({"IMAGEMAGICK_BINARY": path})
                break
                
except ImportError:
    MOVIEPY_AVAILABLE = False

class VideoProcessor:
    def __init__(self):
        self.whisper_model = None
        self.word_colors = KARAOKE_COLORS
    
    def check_whisper(self):
        """Check if whisper is installed"""
        return WHISPER_AVAILABLE
    
    def check_moviepy(self):
        """Check if MoviePy is installed"""
        return MOVIEPY_AVAILABLE
    
    def convert_to_portrait(self, input_path, output_path, add_captions=False, 
                          blur_mode="standard", blur_top=0, blur_bottom=0,
                          caption_settings=None, log_func=None):
        """Convert landscape video to portrait format (9:16) with improved error handling and Unicode support"""
        try:
            if log_func:
                log_func(f"🔄 Converting to portrait format (9:16 aspect ratio)...")
            
            temp_id = str(uuid.uuid4())[:8]
            temp_portrait = os.path.join(os.path.dirname(input_path), f"portrait_temp_{temp_id}.mp4")
            
            # Try the main conversion method first
            conversion_success = self.safe_ffmpeg_portrait_conversion(
                input_path, temp_portrait, blur_mode, blur_top, blur_bottom, log_func
            )
            
            if not conversion_success:
                # Try fallback method
                if log_func:
                    log_func("⚠️ Primary conversion failed, trying fallback method...")
                conversion_success = self.fallback_portrait_conversion(
                    input_path, temp_portrait, blur_mode, blur_top, blur_bottom, log_func
                )
            
            if not conversion_success:
                if log_func:
                    log_func("❌ All conversion attempts failed")
                return False
            
            # Verify the output file was created
            if not os.path.exists(temp_portrait) or os.path.getsize(temp_portrait) == 0:
                if log_func:
                    log_func(f"❌ Output file not created or empty")
                return False
            
            # Verify aspect ratio
            if self.verify_portrait_aspect_ratio(temp_portrait, log_func):
                if log_func:
                    log_func(f"✅ Confirmed proper 9:16 aspect ratio")
            else:
                if log_func:
                    log_func(f"⚠️ WARNING: Video may not be properly converted to portrait format")
            
            # Add captions if requested
            if add_captions and caption_settings:
                if log_func:
                    log_func("✨ Adding animated captions...")
                
                # Create final output with captions
                final_output = os.path.join(os.path.dirname(temp_portrait), f"final_with_captions_{temp_id}.mp4")
                
                if self.add_moviepy_captions(temp_portrait, final_output, caption_settings, log_func):
                    # Clean up temp file and move final to output
                    try:
                        os.remove(temp_portrait)
                        shutil.move(final_output, output_path)
                    except Exception as e:
                        if log_func:
                            log_func(f"   ⚠️ Error moving final file: {str(e)}")
                        # Fallback: just copy temp file
                        shutil.copy2(temp_portrait, output_path)
                        try:
                            os.remove(temp_portrait)
                            if os.path.exists(final_output):
                                os.remove(final_output)
                        except:
                            pass
                else:
                    # Caption addition failed, use video without captions
                    if log_func:
                        log_func("   ⚠️ Caption addition failed, using video without captions")
                    shutil.move(temp_portrait, output_path)
            else:
                # No captions requested, just move the converted file
                shutil.move(temp_portrait, output_path)
            
            if log_func:
                log_func("✅ Portrait conversion complete!")
            return True
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Error converting to portrait: {str(e)}")
            
            # Clean up any temp files
            try:
                if 'temp_portrait' in locals() and os.path.exists(temp_portrait):
                    os.remove(temp_portrait)
            except:
                pass
            
            return False
    
    def safe_ffmpeg_portrait_conversion(self, input_path, output_path, blur_mode, blur_top, blur_bottom, log_func=None):
        """NEW: Safe FFmpeg conversion with Unicode handling and error recovery - UPDATED FOR PROPORTIONAL SCALING"""
        try:
            if log_func:
                log_func("🔧 Using safe FFmpeg conversion...")
            
            target_width = 1080
            target_height = 1920
            
            # Build filter based on blur mode
            if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0):
                if log_func:
                    log_func(f"   Custom blur: {blur_top}% top, {blur_bottom}% bottom")
                
                # Calculate the clear area
                clear_height_percent = (100 - blur_top - blur_bottom) / 100.0
                clear_area_height = int(target_height * clear_height_percent)
                y_offset = int(target_height * blur_top / 100)
                
                if log_func:
                    log_func(f"   Clear area: {clear_area_height}px height at {y_offset}px offset")
                    log_func(f"   Video will scale UP to fill the entire {int(clear_height_percent * 100)}% clear area")
                
                # NEW: Scale video to FILL the clear area completely (scale UP, not down)
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{target_height},"
                    f"gblur=sigma=15[background];"
                    f"[0:v]scale={target_width}:{clear_area_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{clear_area_height}[scaled];"
                    f"[background][scaled]overlay=0:{y_offset}:shortest=1"
                )
            else:
                if log_func:
                    log_func("   Using standard blur mode")
                
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{target_height},"
                    f"gblur=sigma=15[background];"
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2[foreground];"
                    f"[background][foreground]overlay=0:0"
                )
            
            # Build FFmpeg command with safe options
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-filter_complex', filter_string,
                '-map', '0:a?',  # Include audio if available
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'medium',
                '-crf', '23',
                '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
                '-fflags', '+genpts',  # Generate timestamps
                '-movflags', '+faststart',  # Optimize for streaming
                '-y',
                output_path
            ]
            
            # Execute with comprehensive error handling
            return self.execute_ffmpeg_safely(cmd, log_func, timeout=240)  # 4 minute timeout
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Safe FFmpeg conversion error: {str(e)}")
            return False
    
    def fallback_portrait_conversion(self, input_path, output_path, blur_mode, blur_top, blur_bottom, log_func=None):
        """NEW: Fallback conversion method using simpler approach - UPDATED FOR PROPORTIONAL SCALING"""
        try:
            if log_func:
                log_func("🔧 Using fallback conversion method...")
            
            # Much simpler approach but still handle custom blur
            target_width = 1080
            target_height = 1920
            
            if blur_mode == "custom" and (blur_top > 0 or blur_bottom > 0):
                # Calculate clear area for fallback method too
                clear_height_percent = (100 - blur_top - blur_bottom) / 100.0
                clear_area_height = int(target_height * clear_height_percent)
                y_offset = int(target_height * blur_top / 100)
                
                if log_func:
                    log_func(f"   Fallback: Scaling to fill {int(clear_height_percent * 100)}% clear area")
                
                # Simple but effective approach for custom blur
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{target_height},"
                    f"gblur=sigma=10[bg];"
                    f"[0:v]scale={target_width}:{clear_area_height}:force_original_aspect_ratio=increase,"
                    f"crop={target_width}:{clear_area_height}[fg];"
                    f"[bg][fg]overlay=0:{y_offset}"
                )
            else:
                # Simple filter that's less likely to fail
                filter_string = (
                    f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black"
                )
            
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vf', filter_string,
                '-c:v', 'libx264',
                '-c:a', 'copy',  # Just copy audio
                '-preset', 'ultrafast',
                '-crf', '25',
                '-y',
                output_path
            ]
            
            # Execute with shorter timeout
            return self.execute_ffmpeg_safely(cmd, log_func, timeout=120)
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Fallback conversion error: {str(e)}")
            return False
    
    def execute_ffmpeg_safely(self, cmd, log_func=None, timeout=180):
        """NEW: Execute FFmpeg command with comprehensive Unicode and error handling"""
        try:
            if log_func:
                log_func("   Executing FFmpeg command...")
            
            # Set up safe environment
            env = os.environ.copy()
            
            # Force UTF-8 encoding to prevent Unicode issues
            if os.name == 'nt':  # Windows
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONLEGACYWINDOWSSTDIO'] = '1'
            else:
                env['LC_ALL'] = 'C.UTF-8'
                env['LANG'] = 'C.UTF-8'
            
            # Execute subprocess with multiple fallback methods
            for attempt in range(3):
                try:
                    if log_func and attempt > 0:
                        log_func(f"   Retry attempt {attempt + 1}/3...")
                    
                    # Method selection based on attempt
                    if attempt == 0:
                        # First attempt: Full capture with UTF-8
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                            encoding='utf-8',
                            errors='replace'  # Replace invalid characters
                        )
                    elif attempt == 1:
                        # Second attempt: No text capture, just check return code
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=False,  # Don't decode
                            timeout=timeout,
                            env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                    else:
                        # Third attempt: Minimal approach
                        result = subprocess.run(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=timeout,
                            env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                    
                    # Check if successful
                    if result.returncode == 0:
                        if log_func:
                            log_func(f"   ✅ FFmpeg completed successfully")
                        return True
                    else:
                        # Log error if we can decode it safely
                        if attempt < 2:  # Don't spam errors on last attempt
                            try:
                                if hasattr(result, 'stderr') and result.stderr:
                                    if isinstance(result.stderr, str):
                                        error_msg = result.stderr[:200]  # First 200 chars
                                    else:
                                        error_msg = result.stderr.decode('utf-8', errors='replace')[:200]
                                    
                                    if log_func:
                                        log_func(f"   ⚠️ FFmpeg error (attempt {attempt + 1}): {error_msg}")
                            except Exception:
                                if log_func:
                                    log_func(f"   ⚠️ FFmpeg failed (attempt {attempt + 1}) - unknown error")
                        
                        # Wait before retry
                        if attempt < 2:
                            time.sleep(1 + attempt)
                        
                except subprocess.TimeoutExpired:
                    if log_func:
                        log_func(f"   ⏱️ FFmpeg timeout (attempt {attempt + 1}) after {timeout} seconds")
                    if attempt < 2:
                        time.sleep(2)
                    
                except UnicodeDecodeError as ude:
                    if log_func:
                        log_func(f"   🔤 Unicode error (attempt {attempt + 1}): {str(ude)}")
                    if attempt < 2:
                        time.sleep(1)
                    
                except Exception as e:
                    if log_func:
                        log_func(f"   ❌ Execution error (attempt {attempt + 1}): {str(e)}")
                    if attempt < 2:
                        time.sleep(1)
            
            # All attempts failed
            if log_func:
                log_func(f"   ❌ FFmpeg failed after 3 attempts")
            return False
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Fatal FFmpeg execution error: {str(e)}")
            return False
    
    def verify_portrait_aspect_ratio(self, video_path, log_func=None):
        """NEW: Verify that video has proper portrait aspect ratio"""
        try:
            # Use ffprobe to check dimensions
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_streams', video_path
            ]
            
            result = subprocess.run(
                probe_cmd, 
                capture_output=True, 
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                import json
                probe_data = json.loads(result.stdout)
                for stream in probe_data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        width = int(stream.get('width', 0))
                        height = int(stream.get('height', 0))
                        if width > 0 and height > 0:
                            aspect_ratio = height / width
                            if log_func:
                                log_func(f"   📐 Video dimensions: {width}x{height} (aspect ratio: {aspect_ratio:.2f})")
                            
                            # Check if it's properly portrait (9:16 = 1.777...)
                            return aspect_ratio >= 1.5  # Allow some tolerance
                        break
            
            return False  # Couldn't verify
            
        except Exception as e:
            if log_func:
                log_func(f"   ⚠️ Could not verify aspect ratio: {str(e)}")
            return False  # Assume it's fine if we can't verify
    
    def get_font_for_style(self, style):
        """Get the appropriate font for the caption style"""
        font_map = {
            "hormozi": "Impact",
            "gadzhi": "Georgia", 
            "bold": "Impact",
            "classic": "Arial",
            "modern": "Arial-Bold"
        }
        return font_map.get(style, "Arial")
    
    def create_karaoke_style_animation(self, words, video_width, video_height, position="center"):
        """Create Karaoke-style animation: one word pops up at a time."""
        clips = []
        font_to_use = "Impact"
        font_size = int(video_width / 12)
        stroke_width = max(2, int(font_size / 15))
        
        if position == "top":
            y_pos = video_height * 0.33
        elif position == "bottom":
            y_pos = video_height * 0.67
        else:
            y_pos = 'center'
        
        for i, word_info in enumerate(words):
            word_text = word_info['word'].upper().strip()
            if not word_text:
                continue
            
            start_time = word_info['start']
            end_time = word_info.get('end', start_time + 0.5)
            duration = end_time - start_time
            
            color = self.word_colors[i % len(self.word_colors)]
            
            try:
                word_clip = TextClip(
                    word_text,
                    fontsize=font_size,
                    color=color,
                    font=font_to_use,
                    stroke_color='black',
                    stroke_width=stroke_width,
                    method='caption'
                )
                
                word_clip = word_clip.resize(lambda t: 1.2 - 0.2 * min(t * 10, 1) if t < 0.2 else 1.0)
                word_clip = word_clip.set_duration(duration)
                word_clip = word_clip.set_start(start_time)
                word_clip = word_clip.set_position(('center', y_pos))
                
                clips.append(word_clip)
                
            except Exception:
                try:
                    word_clip = TextClip(word_text, fontsize=font_size, color=color, font="Arial-Bold",
                                       stroke_color='black', stroke_width=stroke_width, method='caption'
                                       ).set_duration(duration).set_start(start_time).set_position(('center', y_pos))
                    word_clip = word_clip.resize(lambda t: 1.2 - 0.2 * min(t * 10, 1) if t < 0.2 else 1.0)
                    clips.append(word_clip)
                except:
                    continue
        
        return clips
    
    def create_animated_text(self, txt, style, animation_type, start_time, duration, 
                           video_width, video_height, position="center"):
        """Create animated text clip with various animation styles"""
        font_to_use = self.get_font_for_style(style)
        
        try:
            # Create base text clip based on style
            if style == "hormozi":
                font_size = int(video_width / 12) 
                stroke_width = max(1, int(font_size / 15))
                txt_clip = TextClip(
                    txt, fontsize=font_size, color='white', font=font_to_use,
                    stroke_color='black', stroke_width=stroke_width, method='caption',
                    size=(video_width * 0.8, None), align='center'
                )
            elif style == "gadzhi":
                font_size = int(video_width / 15)
                stroke_width = max(1, int(font_size / 15))
                txt_clip = TextClip(
                    txt, fontsize=font_size, color='#FFD700', font=font_to_use,
                    stroke_color='black', stroke_width=stroke_width, method='caption',
                    size=(video_width * 0.8, None), align='center'
                )
            elif style == "bold":
                font_size = int(video_width / 13)
                stroke_width = max(1, int(font_size / 15))
                txt_clip = TextClip(
                    txt, fontsize=font_size, color='yellow', font=font_to_use,
                    stroke_color='black', stroke_width=stroke_width, method='caption',
                    size=(video_width * 0.8, None), align='center'
                )
            elif style == "classic":
                font_size = int(video_width / 25)
                txt_clip = TextClip(
                    txt, fontsize=font_size, color='white', font=font_to_use,
                    method='caption', size=(video_width * 0.8, None), align='center'
                )
                txt_clip = txt_clip.on_color(
                    size=(txt_clip.w + 20, txt_clip.h + 10),
                    color=(0, 0, 0), col_opacity=0.6
                )
            else:  # modern (TikTok style)
                font_size = int(video_width / 20)
                stroke_width = max(1, int(font_size / 18))
                txt_clip = TextClip(
                    txt, fontsize=font_size, color='white', font=font_to_use,
                    stroke_color='black', stroke_width=stroke_width, method='caption',
                    size=(video_width * 0.9, None), align='center'
                )
                
        except Exception:
            # If font fails, try with default Arial
            font_size = int(video_width / 20)
            stroke_width = max(1, int(font_size / 18))
            txt_clip = TextClip(
                txt, fontsize=font_size, color='white', font='Arial',
                stroke_color='black', stroke_width=stroke_width, method='caption',
                size=(video_width * 0.9, None), align='center'
            )
        
        txt_clip = txt_clip.set_duration(duration)
        
        # Apply animations
        if animation_type == "pop":
            txt_clip = txt_clip.resize(lambda t: 1.2 - 0.2 * min(t * 10, 1) if t < 0.2 else 1.0)
        elif animation_type == "fade":
            txt_clip = txt_clip.crossfadein(0.3).crossfadeout(0.3)
        elif animation_type == "slide":
            txt_clip = txt_clip.set_position(lambda t: ('center', max(50, int(video_height/2 - t * 100))))
        elif animation_type == "zoom":
            txt_clip = txt_clip.resize(lambda t: 0.5 + 0.5 * min(t * 3, 1) if t < 0.33 else 1.0)
        elif animation_type == "bounce":
            txt_clip = txt_clip.set_position(
                lambda t: ('center', int(video_height/2 + 20 * np.sin(2 * np.pi * t * 2)))
            )
        
        if animation_type not in ["slide", "bounce"]:
            if position == "top":
                y_pos = video_height * 0.33
                txt_clip = txt_clip.set_position(('center', y_pos))
            elif position == "bottom":
                y_pos = video_height * 0.67
                txt_clip = txt_clip.set_position(('center', y_pos))
            else:
                if style == "gadzhi":
                    txt_clip = txt_clip.set_position(('center', video_height * 0.7))
                elif style == "classic" and position == "center":
                    txt_clip = txt_clip.set_position(('center', video_height - 150))
                else:
                    txt_clip = txt_clip.set_position(('center', 'center'))
        
        txt_clip = txt_clip.set_start(start_time)
        return txt_clip
    
    def add_moviepy_captions(self, video_path, output_path, caption_settings, log_func=None):
        """Add professional animated captions using MoviePy with better error handling"""
        if not MOVIEPY_AVAILABLE or not WHISPER_AVAILABLE:
            if log_func:
                log_func("⚠️ MoviePy or Whisper not available, skipping captions")
            return False
        
        video = None
        final_video = None
        caption_clips = []
        
        try:
            if log_func:
                log_func("🎬 Loading video with MoviePy...")
            video = VideoFileClip(video_path)
            
            if log_func:
                log_func("🎤 Transcribing audio with Whisper...")
            if self.whisper_model is None:
                if log_func:
                    log_func("   Loading AI model (first time only)...")
                self.whisper_model = whisper.load_model("base")
            
            # Use safer transcription with error handling
            try:
                result = self.whisper_model.transcribe(video_path, word_timestamps=True)
            except Exception as transcribe_error:
                if log_func:
                    log_func(f"⚠️ Whisper transcription error: {str(transcribe_error)}")
                    log_func("   Trying without word timestamps...")
                try:
                    result = self.whisper_model.transcribe(video_path, word_timestamps=False)
                except Exception as fallback_error:
                    if log_func:
                        log_func(f"❌ Whisper fallback failed: {str(fallback_error)}")
                    return False
            
            style = caption_settings.get('style', 'modern')
            animation_type = caption_settings.get('animation', 'pop')
            position = caption_settings.get('position', 'center')
            
            if log_func:
                log_func(f"🎨 Creating {animation_type} animated captions at {position} position...")
            
            if animation_type == "Karaoke Style":
                all_words = []
                for segment in result.get('segments', []):
                    if 'words' in segment and isinstance(segment['words'], list):
                        all_words.extend(segment['words'])
                
                if all_words:
                    caption_clips = self.create_karaoke_style_animation(
                        all_words, video.w, video.h, position
                    )
            else:
                for segment in result['segments']:
                    if 'words' in segment and segment['words']:
                        word_buffer = []
                        start_time = None
                        
                        for i, word_data in enumerate(segment['words']):
                            if start_time is None:
                                start_time = word_data['start']
                            
                            word_buffer.append(word_data['word'].strip())
                            
                            if len(word_buffer) >= 2 or i == len(segment['words']) - 1:
                                text = ' '.join(word_buffer).upper()
                                end_time = word_data.get('end', start_time + 1)
                                duration = end_time - start_time
                                
                                txt_clip = self.create_animated_text(
                                    text, style, animation_type, 
                                    start_time, duration,
                                    video.w, video.h, position
                                )
                                caption_clips.append(txt_clip)
                                
                                word_buffer = []
                                start_time = None
            
            if log_func:
                log_func(f"📝 Created {len(caption_clips)} animated caption segments")
            
            if not caption_clips:
                if log_func:
                    log_func("   No words detected by Whisper, saving video without captions.")
                shutil.copy2(video_path, output_path)
                return True
            
            if log_func:
                log_func("🔄 Rendering video with animated captions...")
            final_video = CompositeVideoClip([video] + caption_clips)
            
            # Write with safer parameters and better error handling
            try:
                final_video.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True,
                    preset='medium',
                    threads=min(4, os.cpu_count()) if os.cpu_count() else 2,  # Limit threads
                    logger='bar',
                    verbose=False  # Reduce verbose output
                )
            except Exception as render_error:
                if log_func:
                    log_func(f"⚠️ Render error: {str(render_error)}")
                    log_func("   Trying with simpler settings...")
                
                # Try with simpler settings
                final_video.write_videofile(
                    output_path,
                    codec='libx264',
                    preset='ultrafast',
                    threads=1,  # Single thread
                    logger=None,  # No progress bar
                    verbose=False
                )
            
            if log_func:
                log_func("✅ Animated captions added successfully!")
            return True
            
        except Exception as e:
            if log_func:
                log_func(f"❌ Error adding captions: {str(e)}")
                log_func("⚠️ Saving video without captions...")
            if os.path.exists(video_path) and not os.path.exists(output_path):
                if video: video.close()
                if final_video: final_video.close()
                time.sleep(1) 
                shutil.copy2(video_path, output_path)
            return False
        
        finally:
            # Clean up resources
            if final_video:
                try: final_video.close()
                except Exception: pass
            if video:
                try: video.close()
                except Exception: pass
            for clip in caption_clips:
                if hasattr(clip, 'close'):
                    try: clip.close()
                    except Exception: pass
            
            # Force garbage collection
            gc.collect()
            time.sleep(0.5)
    
    def get_transcript(self, video_path):
        """Get transcript from video using Whisper with better error handling"""
        if not WHISPER_AVAILABLE:
            return ""
        
        try:
            if self.whisper_model is None:
                self.whisper_model = whisper.load_model("base")
            
            # Try transcription with error handling
            try:
                result = self.whisper_model.transcribe(video_path)
                return result.get('text', '')
            except Exception as e:
                # Try with minimal settings on error
                try:
                    result = self.whisper_model.transcribe(video_path, fp16=False)
                    return result.get('text', '')
                except:
                    return ""
        except:
            return ""