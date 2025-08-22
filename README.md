# 🎙️ Linux TTS Reader

A versatile, real-time **Python text-to-speech (TTS)** tool for Linux.  
It reads text aloud using **Microsoft Edge Neural voices**, processing audio in memory for seamless, gap-free playback.  

The script can read from the **clipboard** or **direct command-line input**, and can be packaged into a standalone executable.

---

## ✨ Features

- **High-Quality Voices** – Uses Microsoft Edge Neural voices via the `edge-tts` library.  
- **Flexible Input** – Read text from the clipboard or from a command-line argument.  
- **Seamless Playback** – Synthesizes and plays audio in parallel (in memory) → no pauses.  
- **Text Cleaning** – Removes extra whitespace & artifacts (can be disabled).  
- **Standalone Build** – Easily packaged into a single executable with PyInstaller.  
- **Controllable** – Start/stop/manage with flags → ideal for keyboard shortcuts.  

---

## 📦 Requirements

- Python **3.9+**
- Debian-based Linux (e.g., Ubuntu, Mint, Debian)
- System tools for clipboard + audio playback

### 🔧 Install Dependencies

1. **System Packages**  
   ```bash
   sudo apt update
   sudo apt install -y libasound2-dev portaudio19-dev xclip
   ```

2. **Python Packages** (use a virtual environment if possible)

   **`requirements.txt`**  
   ```text
   cleantext
   edge-tts
   miniaudio
   simpleaudio
   setproctitle

   ```

   Install them:
   ```bash
   # Create and activate a venv (recommended)
   python3 -m venv venv
   source venv/bin/activate

   # Conda
   conda remove --name tts --all
   conda create --name tts --no-default-packages python=3.9
   conda activate tts

   # Install requirements
   pip install -r requirements.txt
   ```

---

## 🚀 Usage

Clone and enter the repo:
```bash
git clone https://github.com/mjakal/linux-tts-reader.git
cd linux-tts-reader
```

### Command-Line Examples

- **Read from Clipboard (default)**  
  ```bash
  python3 reader.py
  ```
  or explicitly:
  ```bash
  python3 reader.py -c
  ```

- **Read from Text Argument**  
  ```bash
  python3 reader.py -t "Hello world. This is a test."
  ```

- **Change Voice**  
  ```bash
  python3 reader.py -v en-GB-SoniaNeural -t "Using a different voice now."
  ```

- **List Available Voices**  
  ```bash
  python3 reader.py -l
  ```

- **Stop a Running Instance**  
  ```bash
  python3 reader.py -s
  ```

- **Disable Text Cleaning**  
  ```bash
  python3 reader.py --no-clean -t "This text has   extra spaces and [tags]."
  ```

---

## 📦 Build a Standalone App (PyInstaller)

1. **Ensure System Dependencies**
   ```bash
   sudo apt install -y libasound2-dev portaudio19-dev xclip
   ```

2. **Install Build Tools – Choose Your Preferred Option**
   ```bash
   # PyInstaller
   pip install pyinstaller
   
   # Nuitka
   pip install nuitka
   ```

3. **Build Executable - PyInstaller**
   ```bash
   pyinstaller --onefile --name tts-reader reader.py
   ```

4. **Build Executable - Nuitka**
   ```bash
   python -m nuitka --onefile --follow-imports --static-libpython=no --include-module=_cffi_backend reader.py
   ```

5. **Run App**
   ```bash
   cd dist
   chmod +x tts-reader
   ./tts-reader -t "Hello from my new application!"
   ```

---

## ⌨️ Setting Up Keyboard Shortcuts

Bind the script (or built app) to **system-wide hotkeys**:

1. Open system keyboard settings  
   _(e.g., Mint: `Menu → Preferences → Keyboard → Shortcuts`)_

2. Add custom shortcuts:

   - **Start TTS**  
     - **Name**: `Start TTS`  
     - **Command**:  
       - If built: `/full/path/to/dist/tts-reader`  
       - From source: `python3 /full/path/to/reader.py`  
       - _(optionally add flags like `-v en-US-EmmaNeural`)_
     - **Binding**: `Ctrl+Alt+Q`

   - **Stop TTS**  
     - **Name**: `Stop TTS`  
     - **Command**:  
       - If built: `/full/path/to/dist/tts-reader -s`  
       - From source: `python3 /full/path/to/reader.py -s`
     - **Binding**: `Ctrl+Alt+E`

---

You can build the script using nuitka.

```