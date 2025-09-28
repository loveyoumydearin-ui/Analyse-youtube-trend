🤖 Auto-Video-Uploader: AI-Powered YouTube Batch Creator
🌟 Project Summary
Auto-Video-Uploader is a complete Python-based pipeline for automated video content creation and batch uploading to YouTube. It identifies trending topics, generates scripts and visual assets using LLMs and stock image APIs, compiles the final video using MoviePy, and handles authentication, metadata generation, and automatic upload to a YouTube channel.

This project is ideal for content creators looking to rapidly scale their video production.

🚀 Features
Trending Topic Discovery: Automatically pulls current trending topics from YouTube's Most Popular chart.

LLM-Powered Content Generation: Uses OpenRouter/OpenAI to generate video scripts, visual search prompts, titles, descriptions, and dynamic thumbnails.

Automated Asset Sourcing: Integrates with the Pexels API to download relevant stock images for each script segment.

Voiceover Creation: Converts the generated script into an audio file using gTTS.

Video Compilation: Creates a visually appealing 1080p video using MoviePy, featuring a Ken Burns effect, text overlay, background music, and smooth transitions.

Metadata & Thumbnail Generation: Generates click-bait thumbnails via LLM/ImageMagick and complete SEO-friendly metadata.

Batch YouTube Upload: Handles OAuth2 authentication and uploads videos in configurable batches, logging unique video hashes to prevent re-uploading.

🛠️ Prerequisites and Setup
This project requires Python 3.x and several API keys and external libraries.

1. External Dependencies (APIs)
You must obtain the following keys and replace the placeholders in the script (YOUTUBE_API_KEY, OPENROUTER_API_KEY, PEXELS_API_KEY):

API/Service	Purpose	How to Get
YouTube Data API v3	Discover trending topics and upload videos.	Google Cloud Console
OpenRouter / OpenAI	Script, prompt, and metadata generation.	OpenRouter or OpenAI
Pexels API	Download stock images for video visuals.	Pexels Developer

Export to Sheets
2. Required Software
Software	Purpose	Installation Notes
FFmpeg	Required by MoviePy for video encoding.	Install via package manager (apt-get install ffmpeg, brew install ffmpeg).
ImageMagick	Required for creating the dynamic thumbnails.	Install via package manager (brew install imagemagick). Note: If on macOS, ensure the correct path is configured in the script: /opt/homebrew/bin/convert.

Export to Sheets
3. YouTube OAuth 2.0 Credentials
To upload videos, you need to set up OAuth credentials for your Google/YouTube project:

In Google Cloud Console, enable the YouTube Data API v3.

Go to Credentials and create an OAuth client ID of type Desktop app.

Download the JSON file and rename it to client_secret.json in the project root directory.

The first time you run the script, a browser window will open for you to log in and grant permissions. A token.json file will be created to store your credentials for future use.

⚙️ Installation
Clone the repository:

Bash

git clone https://github.com/your-username/auto-video-uploader.git
cd auto-video-uploader
Create a virtual environment (Recommended):

Bash

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install Python dependencies:
(The script imports openai, requests, googleapiclient, moviepy, gtts, Pillow.)

Bash

pip install openai requests google-api-python-client google-auth-oauthlib gTTS moviepy Pillow
Add Background Music:
Place an MP3 file named background_music.mp3 in the root directory. This will be automatically mixed into your videos at a low volume.

▶️ Usage
Configure API Keys: Open the main script file and replace the placeholder values in the PART 1: CONFIGURATION section with your actual keys.

Python

# --- REPLACE THESE PLACEHOLDERS WITH YOUR ACTUAL KEYS --- ⚠️
YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY"
OPENROUTER_API_KEY = "YOUR_OPENROUTER_API_KEY"
PEXELS_API_KEY = "YOUR_PEXELS_API_KEY"
# -------------------------------------------------------------------
Adjust Batch Settings: You can modify the following variables in the script to control the automated process:

Python

VIDEOS_PER_BATCH = 3  # How many videos to create before pausing
TOTAL_BATCHES = 4     # How many batches to run in total
Run the script:

Bash

python3 your_script_name.py
The script will begin the batch process. It will create a token.json file for YouTube authentication on the first run and log the hashes of uploaded videos in uploaded_video_hashes.txt.

🧹 Cleanup and Troubleshooting
The script automatically cleans up most intermediate files (voiceover.mp3, visual_montage.mp4) but creates the following folders:

Folder/File	Purpose	Notes
stock_images/	Stores temporary images from Pexels.	The script tries to clean this up between video runs.
thumbnails/	Stores temporary thumbnail JPGs.	Cleaned up after upload.
final_video_*.mov	The final, compiled video.	Note: If an upload fails, this file is kept for manual review. You may need to delete these periodically.
uploaded_video_hashes.txt	Tracks content that's already been uploaded.	DO NOT DELETE unless you want to re-upload the same content.
token.json	Stores your YouTube OAuth credentials.	Delete this if you need to re-authenticate with a different Google account.

Export to Sheets
Common Troubleshooting:
Image.ANTIALIAS Error: The script includes a patch for this common MoviePy/Pillow issue. If it persists, ensure your Pillow and MoviePy libraries are up-to-date.

Video Compilation Failure: Ensure FFmpeg is correctly installed and accessible on your system's PATH.

Thumbnail Creation Failure: Ensure ImageMagick (convert command) is installed and the path in the script (IMAGEMAGICK_BINARY) is correct for your system.

🤝 Contributing
Contributions are welcome! If you have suggestions for new features, bug fixes, or improvements, please feel free to open an issue or submit a pull request.

📜 License
This project is open-source. I just use the free tools.
