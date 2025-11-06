# Bilibili Scraper - SnapAny Implementation

## Method Overview

Uses [SnapAny.com](https://snapany.com/zh/bilibili) to bypass Bilibili's CDN protection.

## Workflow

1. **Navigate to SnapAny**: Open `https://snapany.com/zh/bilibili`
2. **Wait**: 5 seconds for page load
3. **Input URL**: Paste Bilibili video link
4. **Extract**: Click "提取视频图片" button
5. **Wait for download button**: Monitor for "下载视频" button (10s timeout)
6. **Open popup**: Click download button (opens new tab with video)
7. **Extract video URL**: Get `<video>` source URL from popup
8. **Download**: Save video to `downloads/` folder
9. **Transcribe**: Use transcription tool to convert audio to text
10. **Cleanup**: Delete video file after transcription

## Key Features

- ✅ **Bypasses CDN protection**: SnapAny handles authentication
- ✅ **Browser automation**: Uses Playwright to interact with SnapAny
- ✅ **Video download**: Extracts video URL and downloads it
- ✅ **Local transcription**: Uses transcription tool for Chinese audio
- ✅ **Auto-cleanup**: Deletes downloaded videos after processing

## Configuration

```yaml
bilibili:
  headless: false  # Show browser for debugging
  timeout: 60000  # 60 seconds total timeout
  download_dir: 'downloads'
  transcription_model: 'base'  # Options: 'tiny', 'base', 'small', 'medium', 'large'
  transcription_language: 'zh'  # Chinese
  cleanup_after: true  # Delete video files after transcription
  num_workers: 1  # Sequential only (transcription is resource intensive)
```

## Dependencies

- **Playwright**: Browser automation (already installed)
- **ffmpeg**: Audio extraction (already installed)
- **Speech recognition**: Speech recognition (`pip install speech-recognition`)

## Usage

```python
from scrapers.bilibili_scraper import BilibiliScraper

scraper = BilibiliScraper()
result = scraper.extract("https://www.bilibili.com/video/BV...")

if result['success']:
    print(result['content'])  # Chinese transcript
```

## Testing

```bash
python test_bilibili_snapany.py
```

## Benefits

1. **No direct API calls**: Avoids Bilibili's API restrictions
2. **No manual cookies**: SnapAny handles authentication
3. **Reliable**: Uses third-party service that works
4. **Fast**: Direct video download, no transcoding needed
5. **Accurate**: Uses transcription tool for high-quality transcription

## Limitations

- Requires internet connection
- Depends on SnapAny service availability
- Needs ffmpeg and transcription tool installed
- Processing time: ~5-10 minutes per video

