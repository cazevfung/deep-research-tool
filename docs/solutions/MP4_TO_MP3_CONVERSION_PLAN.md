# Plan: Use MP4-To-MP3-Converter Script

## Overview

Instead of trying to import moviepy in the running Python, we'll use the standalone script from `D:\App Dev\MP4-To-MP3-Converter-main`.

## The Script

Location: `D:\App Dev\MP4-To-MP3-Converter-main\mp4_to_mp3_converter.py`

What it does:
- Uses `moviepy.editor.VideoFileClip` to load video
- Extracts audio: `video.audio`
- Saves as MP3: `audio.write_audiofile(f'{aud_fname}.mp3')`

## The Plan (Not Implemented - Just Planning)

### Option 1: Run the Python script as subprocess

```python
# In our scraper:
import subprocess
import os

# Get the path to the converter script
converter_script = r"D:\App Dev\MP4-To-MP3-Converter-main\mp4_to_mp3_converter.py"

# Run it with Python 3.13 (has moviepy)
audio_path = video_path.replace('.mp4', '.mp3')
cmd = [
    r"C:\Users\fengjunqiao\AppData\Local\Programs\Python\Python313\python.exe",
    "-c",
    f"import moviepy.editor as mp; clip = mp.VideoFileClip(r'{video_path}'); clip.audio.write_audiofile(r'{audio_path}')"
]

subprocess.run(cmd)
```

### Option 2: Call the conversion function directly

The converter script has this logic:
```python
video = moviepy.editor.VideoFileClip(filename)
audio = video.audio
audio.write_audiofile(f'{aud_fname}.mp3')
```

We can replicate this in our code but run it in a subprocess with Python 3.13.

### Option 3: Create a standalone conversion script

Create `convert_mp4_to_mp3.py`:
```python
import sys
import moviepy.editor as mp

video_path = sys.argv[1]
audio_path = sys.argv[2]

video = mp.VideoFileClip(video_path)
video.audio.write_audiofile(audio_path)
video.close()
```

Then call it from the scraper:
```python
subprocess.run([
    r"C:\Users\fengjunqiao\AppData\Local\Programs\Python\Python313\python.exe",
    "convert_mp4_to_mp3.py",
    video_path,
    audio_path
])
```

## Recommended Approach

**Option 3** - Create a simple standalone script that:
1. Takes video path as argument
2. Uses moviepy to convert
3. Returns audio path
4. Can be called from anywhere with Python 3.13

This keeps the conversion logic separate and reusable.

## Implementation Flow

```
1. Download video → downloads/bilibili_xxx.mp4
2. Call convert script with Python 3.13
3. Get back audio file → downloads/bilibili_xxx.mp3 or .wav
4. Load transcription tool
5. Transcribe audio
6. Return transcript
7. Cleanup (if configured)
```

## Benefits

- ✅ No need to install moviepy in the scraper's Python
- ✅ Uses existing Python 3.13 environment
- ✅ Clean separation of concerns
- ✅ Can work even if main Python has different packages

## Files Needed

1. `convert_mp4_to_mp3.py` - Standalone conversion script
2. Update `scrapers/bilibili_scraper.py` to call this script
3. No changes to requirements.txt needed

