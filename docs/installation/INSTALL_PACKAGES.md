# Install Required Packages

The Bilibili scraper works! But you need these packages for transcription:

## Quick Install

Open a terminal in this directory and run:

```bash
pip install speech-recognition ffmpeg-python
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

## What Each Package Does

- **Speech recognition**: Audio transcription (transcribes Chinese audio)
- **ffmpeg-python**: Python wrapper for ffmpeg (extracts audio from video)

## Already Working

✅ Video download via SnapAny  
✅ URL extraction from popup  
✅ Video file saved to `downloads/`  

## Next Step

After installing packages, run the test again:

```bash
python test_bilibili_snapany.py
```

This will now:
1. Download video ✅
2. Transcribe audio ✅
3. Return Chinese transcript ✅
4. Cleanup video file ✅

