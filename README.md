# QuickTitles

<img width="509" height="384" alt="image" src="https://github.com/user-attachments/assets/6d9c4b2e-c9c1-49c0-9c44-e9e453585737" />
<img width="426" height="281" alt="image" src="https://github.com/user-attachments/assets/f4396f49-6b45-4190-9e0e-91091138ad30" />

AI-powered animated subtitle generator. Transcribes video with OpenAI Whisper and renders 
subtitles with customizable styling, animations, and highlighting

Primarily made for YT Shorts, TT, Insta reels but good for any style of content

Works with any video editor since it burns subtitles directly onto the video, no plugin or 
editor integration needed, fully standalone, has its own rendering logic

> ⚠️ Early development, lots of features planned. Released early since a tool like this 
> would have saved me a lot of time when I started out

Tested on Windows. Should work on macOS and Linux but untested

💬 Join the [Discord](https://discord.gg/np4XWvqgQ4) for support, updates, and feature suggestions!

---

# How to use it

Either read the instructions below or just watch [this youtube tutorial](https://youtu.be/RB30zNVdcsk?si=5JeOfCB8lMKOZGcF)

### 1. Download the app
Go to the [Releases](../../releases) page and download the latest `QuickTitles.exe`

### 2. Add your videos
Click **Add Files** and select your video(s). Multiple files are supported and processed in sequence

### 3. Configure your style
Head to the **Settings** tab and adjust font, colors, highlight style, animations, and subtitle position. Hover over any setting for a tooltip explaining what it does

### 4. Transcribe
Click **1. Transcribe**. QuickTitles will extract the audio and run it through Whisper, the model downloads automatically on first use and is cached after that

### 5. Review & edit
Click **2. Review & Edit Transcript** to check the transcription, fix any mistakes

### 6. Render
Once you're happy with the transcript, hit **render** and the finished video will be saved to the `output/` folder, prefixed with `sub_`.

---

# For Developers

Please contribute and add pull requests instead of just forking the code
By working together we can make something genuinely powerful instead of having 500 semi-functional copies of the same thing :)

### Requirements
- Python 3.11+ recommended (built on 3.14)
- ffmpeg — download from [ffmpeg.org](https://ffmpeg.org) and place `ffmpeg.exe` in the 
  project root, or add it to your PATH

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run from source
```bash
python main.py
```

### Build .exe
```bash
pyinstaller QuickTitles.spec
```
