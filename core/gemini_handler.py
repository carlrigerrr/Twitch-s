import random
import time
import threading
import signal
from contextlib import contextmanager

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class TimeoutError(Exception):
    """Custom timeout exception"""
    pass

@contextmanager
def timeout_context(seconds):
    """Context manager for timeouts"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")
    
    # Set up signal handler (Unix/Linux only)
    old_handler = None
    try:
        if hasattr(signal, 'SIGALRM'):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
        yield
    finally:
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
            if old_handler:
                signal.signal(signal.SIGALRM, old_handler)

class GeminiHandler:
    def __init__(self):
        self.api_key = None
        self.model = None
        self.title_cache = []  # Cache to avoid duplicate titles
        self.last_error = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self.timeout_seconds = 30  # 30 second timeout
        
    def is_available(self):
        """Check if Gemini is available"""
        return GEMINI_AVAILABLE
    
    def initialize(self, api_key, log_func=None):
        """Initialize Gemini model if API key is available"""
        if not GEMINI_AVAILABLE or not api_key:
            return False
            
        self.api_key = api_key
        
        try:
            genai.configure(api_key=api_key)
            
            # Try different model names in order of preference
            model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-1.0-pro']
            
            for model_name in model_names:
                try:
                    self.model = genai.GenerativeModel(model_name)
                    # Test if model works with timeout
                    test_response = self._generate_with_timeout("test", 10)
                    if test_response:
                        if log_func:
                            log_func(f"✅ Gemini AI initialized with model: {model_name}")
                        # Clear title cache on initialization
                        self.title_cache = []
                        self.consecutive_failures = 0
                        return True
                except Exception as model_error:
                    if log_func:
                        log_func(f"   Model {model_name} not available: {str(model_error)[:50]}...")
                    continue
            
            # If no models worked
            if log_func:
                log_func("⚠️ No Gemini models available with your API key")
            self.model = None
            return False
            
        except Exception as e:
            if log_func:
                log_func(f"⚠️ Failed to initialize Gemini: {str(e)}")
            self.model = None
            return False
    
    def _generate_with_timeout(self, prompt, timeout_seconds=None):
        """Generate content with timeout protection"""
        if timeout_seconds is None:
            timeout_seconds = self.timeout_seconds
        
        result = [None]  # Use list to store result from thread
        exception = [None]  # Store any exception
        
        def generate_thread():
            try:
                response = self.model.generate_content(prompt)
                result[0] = response
            except Exception as e:
                exception[0] = e
        
        # Start generation in separate thread
        thread = threading.Thread(target=generate_thread)
        thread.daemon = True
        thread.start()
        
        # Wait for completion with timeout
        thread.join(timeout=timeout_seconds)
        
        if thread.is_alive():
            # Timeout occurred
            raise TimeoutError(f"Gemini generation timed out after {timeout_seconds} seconds")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]
    
    def generate_youtube_content(self, transcript, game_name, is_portrait=False, 
                               clip_index=0, log_func=None):
        """Generate title and description using Gemini AI with comprehensive error handling"""
        if not self.model:
            if log_func:
                log_func("⚠️ Gemini model not available")
            return None, None
        
        # Check if we should bypass due to consecutive failures
        if self.consecutive_failures >= self.max_consecutive_failures:
            if log_func:
                log_func(f"⚠️ Bypassing Gemini due to {self.consecutive_failures} consecutive failures")
            return None, None
        
        max_retries = 3
        retry_count = 0
        base_delay = 2  # Base delay for exponential backoff
        
        while retry_count < max_retries:
            try:
                if log_func:
                    if retry_count == 0:
                        log_func(f"🤖 Generating content with Gemini AI (timeout: {self.timeout_seconds}s)...")
                    else:
                        log_func(f"🔄 Retrying Gemini generation (attempt {retry_count + 1}/{max_retries})...")
                
                # Add variety elements for shorts
                variety_elements = [
                    "epic fail", "insane clutch", "no way", "got destroyed", "unbelievable",
                    "what happened", "lucky shot", "close call", "ez clap", "big brain",
                    "outplayed", "instant karma", "plot twist", "calculated", "rip moment",
                    "200 iq", "broken game", "hacker moment", "pure skill", "beginner luck"
                ]
                
                if is_portrait:
                    # Add random element to ensure variety
                    random_element = random.choice(variety_elements)
                    clip_number = clip_index + 1
                    
                    # Prompt for shorts with variety
                    prompt = f"""
                    You are a YouTube Shorts optimization expert. Create a UNIQUE title for gaming short #{clip_number}.
                    
                    Game: {game_name}
                    Video transcript: {transcript[:500]}
                    Theme suggestion: {random_element}
                    
                    Requirements for the title:
                    - EXACTLY 2-3 words maximum
                    - Must be in ALL CAPS
                    - Must be DIFFERENT from these previously used titles: {', '.join(self.title_cache[-5:])}
                    - Try to capture what happened in THIS specific clip
                    - Use the theme "{random_element}" if it fits, otherwise create something unique
                    - Add exactly 2 hashtags after the title: #{game_name.replace(' ', '')} #gaming
                    
                    Requirements for the description:
                    - 2-3 sentences maximum
                    - Make it exciting and engaging
                    - Include relevant gaming keywords
                    - Add these hashtags at the end: #shorts #{game_name.replace(' ', '').lower()} #gaming #viral #fyp
                    
                    Format your response EXACTLY like this:
                    TITLE: [your unique title here]
                    DESCRIPTION: [your description here]
                    
                    Respond quickly and concisely. Do not add extra explanations.
                    """
                else:
                    # Prompt for regular videos
                    prompt = f"""
                    You are a YouTube SEO expert. Create an optimized title and description for a gaming video.
                    
                    Game: {game_name}
                    Video transcript: {transcript[:1000]}
                    
                    Requirements for the title:
                    - 60-80 characters
                    - Include the game name
                    - Use engaging words (Epic, Insane, Unbelievable, etc.)
                    - Make it clickable but not clickbait
                    - Be specific about what happens in THIS clip
                    
                    Requirements for the description:
                    - First 125 characters are crucial (shown in search)
                    - Include what happens in the clip
                    - Add relevant keywords naturally
                    - Include a call-to-action
                    - End with relevant hashtags
                    
                    Format your response EXACTLY like this:
                    TITLE: [your title here]
                    DESCRIPTION: [your description here]
                    
                    Respond quickly and concisely. Do not add extra explanations.
                    """
                
                # Generate content with timeout
                if log_func:
                    log_func("🔄 Sending request to Gemini API...")
                
                response = self._generate_with_timeout(prompt, self.timeout_seconds)
                
                if log_func:
                    log_func("📥 Received response from Gemini API")
                
                if response and response.text:
                    # Parse the response
                    lines = response.text.strip().split('\n')
                    title = None
                    description = None
                    
                    for line in lines:
                        if line.startswith('TITLE:'):
                            title = line.replace('TITLE:', '').strip()
                        elif line.startswith('DESCRIPTION:'):
                            # Get everything after DESCRIPTION:
                            desc_start = lines.index(line)
                            description = '\n'.join(lines[desc_start:]).replace('DESCRIPTION:', '').strip()
                            break
                    
                    # Validate title for shorts
                    if is_portrait and title:
                        # Check if title is unique enough
                        if title in self.title_cache:
                            retry_count += 1
                            if log_func:
                                log_func(f"⚠️ Title duplicate detected, retrying... ({retry_count}/{max_retries})")
                            if retry_count < max_retries:
                                delay = base_delay * (2 ** retry_count) + random.uniform(0, 1)
                                time.sleep(delay)
                                continue
                            else:
                                if log_func:
                                    log_func("⚠️ Max retries reached, using duplicate title")
                        
                        # Add to cache
                        self.title_cache.append(title)
                        # Keep cache size reasonable
                        if len(self.title_cache) > 20:
                            self.title_cache.pop(0)
                    
                    # Success - reset failure counter
                    self.consecutive_failures = 0
                    self.last_error = None
                    
                    if log_func:
                        log_func(f"✅ Gemini generated: {title[:50]}{'...' if len(title) > 50 else ''}")
                    
                    return title, description
                else:
                    raise Exception("Empty response from Gemini API")
                
            except TimeoutError as e:
                retry_count += 1
                self.last_error = str(e)
                if log_func:
                    log_func(f"⏱️ Gemini timeout (attempt {retry_count}/{max_retries}): {str(e)}")
                
            except Exception as e:
                retry_count += 1
                self.last_error = str(e)
                error_msg = str(e)
                
                # Handle specific API errors
                if "quota" in error_msg.lower():
                    if log_func:
                        log_func(f"💸 Gemini quota exceeded: {error_msg}")
                    break  # Don't retry quota errors
                elif "404" in error_msg or "not found" in error_msg.lower():
                    if log_func:
                        log_func(f"🔍 Gemini model not found: {error_msg}")
                    break  # Don't retry model not found errors
                elif "invalid" in error_msg.lower() and "api" in error_msg.lower():
                    if log_func:
                        log_func(f"🔑 Gemini API key invalid: {error_msg}")
                    break  # Don't retry invalid API key
                else:
                    if log_func:
                        log_func(f"❌ Gemini error (attempt {retry_count}/{max_retries}): {error_msg[:100]}")
                
            # Wait before retry with exponential backoff
            if retry_count < max_retries:
                delay = base_delay * (2 ** retry_count) + random.uniform(0, 1)
                if log_func:
                    log_func(f"⏳ Waiting {delay:.1f} seconds before retry...")
                time.sleep(delay)
        
        # All retries failed
        self.consecutive_failures += 1
        
        if log_func:
            log_func(f"❌ Gemini generation failed after {max_retries} attempts")
            if self.consecutive_failures >= self.max_consecutive_failures:
                log_func(f"⚠️ Disabling Gemini temporarily after {self.consecutive_failures} consecutive failures")
        
        return None, None
    
    def test_api_key(self, api_key):
        """Test if an API key is valid with timeout"""
        if not GEMINI_AVAILABLE:
            return False, "Gemini library not available"
        
        try:
            genai.configure(api_key=api_key)
            
            # Try to create a model and generate something simple with timeout
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Use timeout for test
            result = [None]
            exception = [None]
            
            def test_thread():
                try:
                    response = model.generate_content("Say hello")
                    result[0] = response
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=test_thread)
            thread.daemon = True
            thread.start()
            thread.join(timeout=15)  # 15 second timeout for test
            
            if thread.is_alive():
                return False, "API test timed out after 15 seconds"
            
            if exception[0]:
                raise exception[0]
            
            if result[0] and result[0].text:
                return True, result[0].text[:100]
            else:
                return False, "Invalid API key or no response"
                
        except Exception as e:
            error_msg = str(e)
            
            # Provide helpful error messages
            if "404" in error_msg and "model" in error_msg:
                return False, ("Model not available. This might be due to:\n"
                             "1. API key restrictions\n"
                             "2. Region limitations\n"
                             "3. Model availability")
            elif "API key not valid" in error_msg or "invalid" in error_msg.lower():
                return False, ("Invalid API key. Please check:\n"
                             "1. You copied the entire key\n"
                             "2. The key hasn't expired\n"
                             "3. You have the correct permissions")
            elif "quota" in error_msg.lower():
                return False, ("Quota exceeded. Please check:\n"
                             "1. Your API usage limits\n"
                             "2. Billing status\n"
                             "3. Try again later")
            else:
                return False, f"Error: {error_msg}"
    
    def reset_failure_counter(self):
        """Reset the consecutive failure counter"""
        self.consecutive_failures = 0
        self.last_error = None
    
    def get_status(self):
        """Get current status of Gemini handler"""
        return {
            'available': GEMINI_AVAILABLE,
            'initialized': self.model is not None,
            'api_key_set': self.api_key is not None,
            'consecutive_failures': self.consecutive_failures,
            'bypassed': self.consecutive_failures >= self.max_consecutive_failures,
            'last_error': self.last_error,
            'cache_size': len(self.title_cache)
        }