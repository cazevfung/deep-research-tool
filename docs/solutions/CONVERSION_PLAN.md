# MP4 to MP3 Conversion Plan (No moviepy)

## Problem
moviepy isn't accessible in the Python environment being used by the scraper.

## Solution: Direct FFmpeg subprocess call

We can use ffmpeg directly via subprocess WITHOUT needing moviepy installed.

### The Plan:

1. **Download video** ✅ (already working)
2. **Call ffmpeg directly** to convert video to audio:
   ```python
   subprocess.run([
       'ffmpeg',
       '-i', video_path,
       '-vn',  # No video
       '-acodec', 'libmp3lame',
       '-ab', '192k',
       '-ar', '44100',
       '-ac', '2',
       '-y',  # Overwrite
       audio_path
   ])
   ```
3. **Transcribe audio** ✅
4. **Cleanup files** ✅

### Why this will work:

- ffmpeg is a command-line tool (independent of Python packages)
- No need for moviepy or any Python packages
- Direct and reliable conversion
- You already have ffmpeg installed via Chocolatey

### Process Flow:

```
Video downloaded → ffmpeg conversion → Audio file → Transcription → Transcript
```

### Implementation:

Just replace the moviepy section with a subprocess call to ffmpeg.

