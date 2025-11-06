# Absolute vs Relative Paths

## The Problem

When we have a file at: `downloads\bilibili_1761622179.mp3`

This is a **relative path** - it depends on where you're running the script from.

## Example

If you're in: `D:\App Dev\Research Tool\`
- Relative: `downloads\video.mp3` ✅ Works

If you're in: `D:\App Dev\`
- Relative: `downloads\video.mp3` ❌ Fails (downloads folder doesn't exist here)

## Absolute Path

**Absolute path** is the full path from the root:
```
D:\App Dev\Research Tool\downloads\bilibili_1761622179.mp3
```

This **always works** no matter where you run the script from.

## What I Fixed

```python
# Before (relative path)
audio_path = "downloads\\bilibili_xxx.mp3"

# After (absolute path)
audio_path = os.path.abspath("downloads\\bilibili_xxx.mp3")
# Result: "D:\\App Dev\\Research Tool\\downloads\\bilibili_xxx.mp3"
```

Now the transcription tool can find the file even if the working directory changes!

