# QuickTitles
AI-powered animated subtitle generator. Transcribes video with OpenAI Whisper and renders subtitles with customizable styling

Works for any video editor since it burns the subtitles on any video manually (doesn't use a specific video editor, has its own rendering functionality)

This is still in very early stage of development, I have lots of features I'd like to add planned, just thought id release this as soon as possible since it would have saved me lots of time if a tool like this existed when i first started

Should work for any OS though i only tested it on Windows
Join https://discord.gg/np4XWvqgQ4 for support and updates
Any feature suggestions are highly appreciated!

# For developers

## Python version
Built and tested on Python 3.14. If you have dependency install issues, 
Python 3.11 is recommended for running from source.

## Requirements
- ffmpeg — download from https://ffmpeg.org and place `ffmpeg.exe` in the project root (or add to PATH)

## Install dependencies
pip install -r requirements.txt

## Run
python main.py

## Build .exe
pyinstaller QuickTitles.spec
