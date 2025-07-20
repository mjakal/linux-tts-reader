# linux-tts-reader

A simple Python-based text-to-speech (TTS) tool that reads selected text from your clipboard using Microsoft's Edge Neural voices via the `edge-tts` library. It supports background playback and can be controlled via keyboard shortcuts.

## Features

- Text-to-speech using Microsoft's `edge-tts`
- Reads selected (primary) text from clipboard
- Voice selection by voice name
- Plays audio using `mpv`
- Starts and stops via custom keyboard shortcuts
- Temporary files and subprocesses are cleaned up automatically

## Requirements

- Python 3.7+
- Linux with X11 clipboard support (tested on Linux Mint)
- `edge-tts` Python library
- `xclip` (for clipboard access)
- `mpv` (for audio playback)

### Install dependencies

```
pip install edge-tts
sudo apt install xclip mpv
```

## Usage

### Clone the Repository

```
git clone https://github.com/mjakal/linux-tts-reader.git
cd linux-tts-reader
```
### Run Manually

Copy any text to your primary clipboard (select it with your mouse).

```
python3 start.py en-US-EmmaNeural
```

You can list all available voices using:

```
python3 reader.py -l
```

## Setting Up Keyboard Shortcuts (Linux Mint Cinnamon)

### Start Reading (Assign a Shortcut)

1. Open Menu → Preferences → Keyboard
2. Go to the Custom Shortcuts tab
3. Click Add custom shortcut
4. Enter the following:
   - Name: Start TTS
   - Command: python3 /full/path/to/reader.py -v en-US-EmmaNeural
5. Click Apply, then assign a key combination (e.g., Ctrl+Alt+Q)

### Stop Reading (Assign a Shortcut)

1. Repeat the steps above to add another shortcut:
   - Name: Stop TTS
   - Command: python3 /full/path/to/reader.py -s
2. Assign a different key combination (e.g., Ctrl+Alt+E)

These shortcuts allow you to start and stop TTS playback from anywhere on your desktop environment.