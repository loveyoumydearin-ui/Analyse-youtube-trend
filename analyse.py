import os
import openai
import requests
import time
import json
import re 
import sys
import hashlib
import signal # NEW: For graceful exit
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from json.decoder import JSONDecodeError

# MoviePy/Pillow Imports and Patches
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, ImageClip, concatenate_videoclips, CompositeAudioClip
from moviepy.config import change_settings 
from gtts import gTTS 
import shutil 

# --- CRITICAL FIX: PATCH for MOVIEPY/PILLOW (PIL) ANTIALIAS ERROR ---
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        if hasattr(Image.Resampling, 'LANCZOS'):
            Image.ANTIALIAS = Image.Resampling.LANCZOS
            print("Pillow ANTIALIAS constant successfully patched (using Image.Resampling.LANCZOS).")
        elif hasattr(Image, 'LANCZOS'):
             Image.ANTIALIAS = Image.LANCZOS
             print("Pillow ANTIALIAS constant successfully patched (using Image.LANCZOS).")
        else:
             print("Warning: Could not find LANCZOS or ANTIALIAS. MoviePy may fail.")
except ImportError:
    print("Warning: Pillow is not installed.")
except Exception as e:
    print(f"Warning: Could not apply Pillow patch: {e}")
# ------------------------------------------------------------------


# ######################################################################
# #################### PART 1: CONFIGURATION #############################
# ######################################################################

# ⚠️ --- REPLACE THESE PLACEHOLDERS WITH YOUR ACTUAL KEYS --- ⚠️
YOUTUBE_API_KEY = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" # Your YouTube Data API Key
OPENROUTER_API_KEY = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" # Your OpenRouter/LLM API Key
PEXELS_API_KEY = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" # Your Pexels API Key
# -------------------------------------------------------------------

PEXELS_BASE_URL = "https://api.pexels.com/v1/"
BACKGROUND_MUSIC_PATH = "background_music.mp3" 

# --- BATCH PROCESSING ---
VIDEOS_PER_BATCH = 3
TOTAL_BATCHES = 4

# --- UPLOAD & LOGGING ---
PROCESSED_LOG_FILE = 'uploaded_video_hashes.txt' 
HASH_BUF_SIZE = 65536
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.force-ssl'] # Added force-ssl scope for thumbnail upload

# --- MOVIEPY/IMAGEMAGICK FIX (For macOS) ---
try:
    IMAGEMAGICK_BINARY = "/opt/homebrew/bin/convert" 
    change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})
    print(f"Set ImageMagick path to: {IMAGEMAGICK_BINARY}")
except Exception: 
    print("Warning: Could not set ImageMagick path. Check ImageMagick installation.")
# --------------------------------------------

USED_TOPICS = set()
STOCK_IMAGE_FOLDER = "stock_images"
THUMBNAIL_FOLDER = "thumbnails" # NEW: Thumbnail folder
if not os.path.exists(STOCK_IMAGE_FOLDER):
    os.makedirs(STOCK_IMAGE_FOLDER)
if not os.path.exists(THUMBNAIL_FOLDER): # NEW: Create thumbnail folder
    os.makedirs(THUMBNAIL_FOLDER)

# Initialize OpenAI Client for Content Generation
try:
    openai_client = openai.OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1" 
    )
except Exception as e:
    print(f"Failed to initialize OpenAI client for content generation: {e}")
    openai_client = None


# ######################################################################
# #################### PART 2: VIDEO CREATION FUNCTIONS ##################
# ######################################################################

def get_trending_topic(api_key, used_topics, region_code='US', max_results=20):
    """Fetches a unique trending YouTube video title."""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        request = youtube.videos().list(part="snippet", chart="mostPopular", regionCode=region_code, maxResults=max_results)
        response = request.execute()
        for item in response['items']:
            title = item['snippet']['title']
            if title not in used_topics:
                used_topics.add(title)
                return title
        return None
    except Exception as e:
        print(f"An error occurred while fetching YouTube data: {e}")
        return None

def generate_script(topic):
    """Generates a video script."""
    if not openai_client: return None
    try:
        prompt_content = (f"Write a 45-second script for a friendly, engaging YouTube video about the trending topic: '{topic}'. "
            f"The script must include a strong call to action at the end. Only return the script text, nothing else.")
        response = openai_client.chat.completions.create(model="openai/gpt-3.5-turbo", messages=[
                {"role": "system", "content": "You are a creative scriptwriter."},
                {"role": "user", "content": prompt_content}], max_tokens=250, temperature=0.8)
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"An error occurred while generating script: {e}")
        return None

def generate_visual_prompts(script, required_prompts=5): 
    """Generates visual search queries."""
    if not openai_client: return []
    try:
        prompt_content = f"Based on the following script, generate a list of {required_prompts} concise, specific, visual search queries. Return ONLY the list, with each query on a new line.\n\nSCRIPT:\n---\n{script}"
        response = openai_client.chat.completions.create(model="openai/gpt-3.5-turbo", messages=[
                {"role": "system", "content": "You are a creative visual prompt generator."},
                {"role": "user", "content": prompt_content}], max_tokens=required_prompts * 30, temperature=0.3)
        return [p.strip() for p in response.choices[0].message.content.strip().split('\n') if p.strip()]
    except Exception: return []

def download_stock_images(prompts):
    """Searches Pexels and saves images locally."""
    if not PEXELS_API_KEY: 
        print("\n!!! WARNING: Pexels API Key is not set. Skipping automated image download.")
        return False
    try: shutil.rmtree(STOCK_IMAGE_FOLDER); os.makedirs(STOCK_IMAGE_FOLDER)
    except Exception: pass
    headers = {"Authorization": PEXELS_API_KEY}
    success_count = 0
    for i, query in enumerate(prompts):
        try:
            response = requests.get(PEXELS_BASE_URL + "search", headers=headers, params={"query": query, "per_page": 1, "orientation": "landscape"})
            data = response.json()
            if data['photos']:
                photo_url = data['photos'][0]['src']['large']
                image_response = requests.get(photo_url, stream=True)
                filename = f"image_{i+1}_{query.replace(' ', '_')[:20]}.jpg"
                file_path = os.path.join(STOCK_IMAGE_FOLDER, filename)
                with open(file_path, 'wb') as f:
                    for chunk in image_response.iter_content(chunk_size=8192): f.write(chunk)
                success_count += 1
        except Exception: pass
    return success_count > 0

def create_text_and_voiceover(script):
    """Generates a voiceover audio file."""
    tts = gTTS(text=script, lang='en')
    audio_path = "voiceover.mp3"
    tts.save(audio_path)
    return audio_path

def create_visual_video(voiceover_path, script_lines):
    """Creates a slideshow video with Ken Burns effect and crossfades."""
    try:
        audio_clip = AudioFileClip(voiceover_path)
        # FIX APPLIED HERE: Used attribute .duration instead of function .duration()
        video_duration = audio_clip.duration 
        script_segments = [line.strip() for line in script_lines if line.strip()]
        num_segments = len(script_segments)
        if video_duration == 0 or num_segments == 0: 
             print("ERROR: Voiceover duration or script length is zero. Cannot create video.")
             return None
        segment_duration = video_duration / num_segments
        transitioned_clips = []
        image_files = sorted([f for f in os.listdir(STOCK_IMAGE_FOLDER) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        if not image_files: image_files = [None] * num_segments
        elif len(image_files) < num_segments: image_files = (image_files * (num_segments // len(image_files) + 1))[:num_segments]

        for i, (text, image_file) in enumerate(zip(script_segments, image_files)):
            clip_size = (1920, 1080)
            if image_file:
                img_path = os.path.join(STOCK_IMAGE_FOLDER, image_file)
                visual_clip = ImageClip(img_path).set_duration(segment_duration)
                visual_clip = visual_clip.resize(lambda t: 1.1 - 0.1 * t / segment_duration).set_position('center')
            else:
                visual_clip = ImageClip(color=(0,0,0), size=clip_size).set_duration(segment_duration)
            
            text_clip = TextClip(text, fontsize=45, color='white', font="Arial-Bold", bg_color="black", size=(clip_size[0]*0.9, None), 
                                 method='caption', stroke_color='black', stroke_width=2.5).set_opacity(0.85).set_pos(("center", "bottom")).set_duration(segment_duration)
            segment_clip = CompositeVideoClip([visual_clip, text_clip], size=clip_size)
            
            if i > 0: segment_clip = segment_clip.crossfadein(0.3)
            transitioned_clips.append(segment_clip)
            
        final_visual_clip = concatenate_videoclips(transitioned_clips, method="compose").set_duration(video_duration)
        output_filename = "visual_montage.mp4"
        final_visual_clip.write_videofile(output_filename, codec="libx264", fps=24, logger=None) 
        return output_filename
    except Exception as e:
        print(f"An error occurred during video creation: {e}")
        return None

def compile_final_video(visual_video_path, voiceover_path, title_text, video_num):
    """Combines montage, audio, and title overlay."""
    safe_title = "".join(c for c in title_text if c.isalnum() or c in (' ', '_')).rstrip()
    output_filename = f"final_video_{video_num}_{safe_title[:20].replace(' ', '_')}.mov" 
    
    try:
        main_clip = VideoFileClip(visual_video_path)
        voiceover_clip = AudioFileClip(voiceover_path)
        title_clip = TextClip(f"🤯 TRENDING: {title_text[:50]}...", fontsize=70, color='yellow', font="Arial-Bold", bg_color="black")
        title_clip = title_clip.set_pos(("center", "top")).set_duration(3).set_opacity(0.8)
        final_video = CompositeVideoClip([main_clip, title_clip])

        audio_clips_to_merge = [voiceover_clip]
        if os.path.exists(BACKGROUND_MUSIC_PATH):
            music_clip = AudioFileClip(BACKGROUND_MUSIC_PATH).volumex(0.3).loop(duration=main_clip.duration).set_duration(main_clip.duration)
            audio_clips_to_merge.append(music_clip)

        final_audio = CompositeAudioClip(audio_clips_to_merge)
        final_video = final_video.set_audio(final_audio)

        final_video.write_videofile(output_filename, codec="libx264", audio_codec="pcm_s16le", fps=24 )
        return output_filename
    
    except Exception as e:
        print(f"An error occurred during final video compilation: {e}")
        return None

# ######################################################################
# #################### PART 3: UPLOAD & LOGIC FUNCTIONS ##################
# ######################################################################

def generate_and_set_thumbnail(client, youtube_service, video_id, video_title):
    """Generates a text-based thumbnail using ImageMagick and uploads it."""
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, f"thumb_{video_id}.jpg")
    
    try:
        # 1. LLM: Get punchy text for the thumbnail
        prompt = f"For a YouTube video titled '{video_title}', generate the single most attention-grabbing, short (1-5 word) phrase to put on a thumbnail. Return ONLY the phrase."
        response = client.chat.completions.create(model="deepseek/deepseek-r1-0528-qwen3-8b:free", messages=[
                      {"role": "system", "content": "You are a clickbait title generator."},
                      {"role": "user", "content": prompt}], max_tokens=15, temperature=0.7)
        thumbnail_text = response.choices[0].message.content.strip().upper()
        print(f"  -> Generated Thumbnail Text: '{thumbnail_text}'")
        
        # 2. ImageMagick: Create the image (Requires ImageMagick `convert` binary)
        if not os.path.exists(IMAGEMAGICK_BINARY):
            print("  -> WARNING: ImageMagick not found. Skipping thumbnail creation.")
            return False

        # ImageMagick Command: Create a 1280x720 red background, add yellow text
        magick_command = (
            f'{IMAGEMAGICK_BINARY} -size 1280x720 xc:red '
            f'-font Arial-Bold -pointsize 100 -fill yellow -stroke black -strokewidth 5 '
            f'-gravity center -annotate 0 "{thumbnail_text}" '
            f'{thumbnail_path}'
        )
        os.system(magick_command)
        
        if not os.path.exists(thumbnail_path):
             print("  -> ERROR: ImageMagick failed to create the thumbnail file.")
             return False

        # 3. YouTube API: Upload the thumbnail
        media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
        youtube_service.thumbnails().set(videoId=video_id, media_body=media).execute()
        print("  -> Thumbnail uploaded successfully.")
        return True
        
    except HttpError as e:
        print(f"  -> ERROR uploading thumbnail (HTTP): {e.content.decode()}")
        return False
    except Exception as e:
        print(f"  -> ERROR during thumbnail creation/upload: {e}")
        return False
    finally:
        # Cleanup the local thumbnail file
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            
def get_processed_videos_hashes():
    """Reads the log file and returns a set of processed video SHA-256 hashes."""
    if not os.path.exists(PROCESSED_LOG_FILE): open(PROCESSED_LOG_FILE, 'a').close(); return set()
    with open(PROCESSED_LOG_FILE, 'r') as f: return {line.strip() for line in f}

def log_processed_video_hash(video_hash):
    """Appends a video hash to the log file."""
    with open(PROCESSED_LOG_FILE, 'a') as f: f.write(f"{video_hash.strip()}\n")

def calculate_file_hash(filepath, hash_algorithm='sha256'):
    """Calculates the cryptographic hash (checksum) of a file."""
    if not os.path.exists(filepath): return None
    try:
        hasher = hashlib.new(hash_algorithm)
        with open(filepath, 'rb') as f:
            while True:
                data = f.read(HASH_BUF_SIZE)
                if not data: break
                hasher.update(data)
        return hasher.hexdigest()
    except Exception: return None

def get_authenticated_services():
    """Handles Google API authentication for YouTube upload."""
    creds = None
    if os.path.exists('token.json'): creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try: creds.refresh(Request())
            except RefreshError:
                flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token: token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def safe_json_load_and_clean(json_string):
    """Attempts to load a JSON string, cleaning up common LLM output errors."""
    match = re.search(r'(\{[\s\S]*\})', json_string.strip())
    cleaned_string = match.group(1).strip() if match else json_string.strip()
    try: return json.loads(cleaned_string)
    except JSONDecodeError as e:
        print(f"FATAL JSON PARSING ERROR: Could not parse cleaned JSON string. Error: {e}")
        return None

def get_video_metadata(client, video_name):
    """Generates metadata for a SINGLE video using OpenRouter LLM."""
    prompt = f"""You are a helpful assistant for creating YouTube video metadata. For the video name: '{video_name}', generate a catchy title, a creative description, and a list of 10-15 keywords. YOUR RESPONSE MUST BE A SINGLE, VALID, RAW JSON OBJECT."""
    retries = 0; max_retries = 3; delay = 30
    while retries < max_retries:
        try:
            response = client.chat.completions.create(model="deepseek/deepseek-r1-0528-qwen3-8b:free", messages=[
                      {"role": "system", "content": "Generate metadata in JSON format: {'original_file_name':'name','title':'title','description':'desc','tags':'tag1,tag2'}"},
                      {"role": "user", "content": prompt}], response_format={"type": "json_object"})
            parsed_data = safe_json_load_and_clean(response.choices[0].message.content)
            if parsed_data and parsed_data.get('title'): return parsed_data
            else: raise ValueError("LLM returned unusable or invalid JSON.")
        except Exception as e:
            print(f"Metadata generation failed: {e}"); retries += 1
            if retries < max_retries: time.sleep(delay); delay *= 1.5
    return None

def upload_video_to_youtube(youtube_service, video_path, title, description, tags):
    """Uploads a local video file to YouTube."""
    body = {'snippet': {'title': title, 'description': description, 'tags': [t.strip() for t in tags.split(',')] if tags else [], 'categoryId': '27'},
            'status': {'privacyStatus': 'public'}}
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    try:
        print(f"Starting YouTube upload for '{os.path.basename(video_path)}'...")
        request = youtube_service.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
        response = request.execute()
        print("Video uploaded successfully!")
        return response['id'] # Return the video ID for thumbnail upload
    except HttpError as e:
        print(f"An HTTP error occurred during YouTube upload:\n{e.content.decode()}")
        return None

def cleanup_intermediate_files(files_to_delete):
    """Deletes the specified files."""
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception as e: print(f"  -> ERROR deleting {file_path}: {e}")

def signal_handler(sig, frame):
    """Gracefully handles Ctrl+C (KeyboardInterrupt)."""
    print("\n\n👋 Ctrl+C detected! Shutting down gracefully...")
    sys.exit(0)

# ######################################################################
# #################### PART 4: MAIN EXECUTION ############################
# ######################################################################

if __name__ == '__main__':
    
    # NEW: Register the signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # 1. Initialize Uploader Service
    try:
        youtube_service = get_authenticated_services()
    except Exception as e:
        print(f"FATAL: YouTube authentication failed. Check client_secret.json and token.json. Error: {e}")
        sys.exit(1)

    uploader_client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    processed_video_hashes = get_processed_videos_hashes()
    
    for batch_num in range(1, TOTAL_BATCHES + 1):
        print(f"\n=======================================================")
        print(f"| Starting Batch {batch_num} of {TOTAL_BATCHES} ({VIDEOS_PER_BATCH} videos per batch) |")
        print(f"=======================================================")
        
        videos_in_batch = 0
        
        while videos_in_batch < VIDEOS_PER_BATCH:
            video_num = (batch_num - 1) * VIDEOS_PER_BATCH + (videos_in_batch + 1)
            print(f"\n--- Processing Video #{video_num} ---")
            
            # --- CREATION PHASE ---
            trending_topic = get_trending_topic(YOUTUBE_API_KEY, USED_TOPICS)
            if not trending_topic: 
                print("Failed to find a unique trending topic.")
                break
            
            print(f"Found a trending topic: '{trending_topic}'")
            script = generate_script(trending_topic)
            if not script: time.sleep(5); continue
                
            script_lines = [line.strip() for line in script.split('.') if line.strip()] 
            visual_prompts = generate_visual_prompts(script, len(script_lines))
            download_stock_images(visual_prompts)
            voiceover_path = create_text_and_voiceover(script)
            visual_video_path = create_visual_video(voiceover_path, script_lines)
            final_video_path = compile_final_video(visual_video_path, voiceover_path, trending_topic, video_num)
            
            intermediate_files = [voiceover_path, visual_video_path]
            
            if not final_video_path or not os.path.exists(final_video_path):
                print(f"Video #{video_num} failed to compile. Skipping upload.")
                cleanup_intermediate_files(intermediate_files)
                time.sleep(5); continue
            
            # --- UPLOAD PHASE ---
            
            # 2. Hash Check (Uniqueness)
            file_content_hash = calculate_file_hash(final_video_path, 'sha256')
            if file_content_hash in processed_video_hashes:
                 print(f"Video {final_video_path} already uploaded (Hash found). Deleting local file and skipping.")
                 os.remove(final_video_path)
                 cleanup_intermediate_files(intermediate_files)
                 videos_in_batch += 1
                 continue
                 
            # 3. Get Metadata
            metadata = get_video_metadata(uploader_client, final_video_path)

            if not metadata:
                print(f"Failed to get metadata. Deleting video and retrying next video.")
                os.remove(final_video_path)
                cleanup_intermediate_files(intermediate_files)
                time.sleep(60); continue
                
            # 4. Upload
            video_id = upload_video_to_youtube(
                youtube_service, 
                final_video_path, 
                metadata.get('title'), 
                metadata.get('description'), 
                metadata.get('tags')
            )
            
            # 5. Thumbnail and Final Cleanup
            if video_id:
                # NEW: Generate and set thumbnail
                generate_and_set_thumbnail(uploader_client, youtube_service, video_id, metadata.get('title'))
                
                log_processed_video_hash(file_content_hash)
                print(f"Successfully uploaded and logged hash {file_content_hash[:10]}... for {final_video_path}.")
                cleanup_intermediate_files(intermediate_files + [final_video_path])
                videos_in_batch += 1
            else:
                print(f"WARNING: YouTube upload failed for {final_video_path}. Keeping final video for manual review/retry.")
                cleanup_intermediate_files(intermediate_files)
                time.sleep(5) 

        # Pause between batches
        if batch_num < TOTAL_BATCHES:
            pause_time = 600 
            print(f"\n--- Batch {batch_num} complete. Pausing for {pause_time // 60} minutes... ---")
            time.sleep(pause_time)
            
    print("\n\nAll batches complete. Program finished.")