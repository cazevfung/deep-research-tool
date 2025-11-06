# Install moviepy in the correct Python environment

The error shows moviepy isn't being found. Install it in the same Python environment where you're running the script.

## Install moviepy

Open a terminal in this directory and run:

```bash
pip install moviepy
```

Or if that doesn't work:

```bash
python -m pip install moviepy
```

Or using the full Python path:

```bash
C:\Users\fengjunqiao\AppData\Local\Microsoft\WindowsApps\python.exe -m pip install moviepy
```

## Verify Installation

Check if moviepy is installed:

```bash
python -c "import moviepy; print(moviepy.__version__)"
```

If you see a version number, it's installed correctly.

## Then Run Test

```bash
python test_bilibili_snapany.py
```

The output will show the step-by-step process:
- ✅ STEP 1: Video downloaded
- ✅ STEP 2: Converting to audio
- ✅ STEP 3: Loading transcription tool
- ✅ STEP 4: Transcribing
- ✅ STEP 5: Complete

