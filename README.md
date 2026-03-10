# QuickTitles

<img width="1017" height="767" alt="image" src="https://github.com/user-attachments/assets/6d9c4b2e-c9c1-49c0-9c44-e9e453585737" />
<img width="852" height="561" alt="image" src="https://github.com/user-attachments/assets/f4396f49-6b45-4190-9e0e-91091138ad30" />

AI-powered animated subtitle generator. Transcribes video with OpenAI Whisper and renders 
subtitles with customizable styling, animations, and highlighting

Primarily made for YT Shorts, TT, Insta reels but good for any style of content

Works with any video editor since it burns subtitles directly onto the video, no plugin or 
editor integration needed, fully standalone, has its own rendering logic

> ⚠️ Early development — lots of features planned. Released early since a tool like this 
> would have saved me a lot of time when I started out

Tested on Windows. Should work on macOS and Linux but untested

💬 Join the [Discord](https://discord.gg/np4XWvqgQ4) for support, updates, and feature suggestions!

---

# For Developers

## Requirements
- Python 3.11+ recommended (built on 3.14)
- ffmpeg — download from [ffmpeg.org](https://ffmpeg.org) and place `ffmpeg.exe` in the 
  project root, or add it to your PATH

## Install dependencies
```bash
pip install -r requirements.txt
```

## Run from source
```bash
python main.py
```

## Build .exe
```bash
pyinstaller QuickTitles.spec
```
