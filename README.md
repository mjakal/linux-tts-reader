# 🎙️ Linux TTS Reader (Client-Server Architecture)

A blazing fast, real-time **Text-to-Speech (TTS)** tool for Linux.

It uses a **Client/Server architecture** to solve the "cold start" problem of Python audio libraries.

1. **Server (Python):** Runs in the background, keeping heavy AI voice models and audio drivers loaded in memory.
2. **Client (Bash):** A lightweight (<2KB) script that starts instantly, sends text to the server via a local socket, and exits.

---

## ✨ Features

* **Instant Startup** – No Python loading lag. The Bash client executes in milliseconds.
* **Zero Configuration** – The client automatically launches the server if it's not running.
* **High-Quality Voices** – Uses **Microsoft Edge Neural voices** (free, no API key required).
* **Gapless Playback** – Synthesizes and buffers audio in parallel.
* **Smart Clipboard Reading** – Reads selected text (highlight) or clipboard content.
* **Text Cleaning** – Removes extra whitespace & artifacts automatically.

---

## 📦 Requirements

### 1. System Tools (Client & Server)
You need `jq` (for JSON), `netcat` (for socket communication), and audio libraries.

```bash
sudo apt update
sudo apt install -y libasound2-dev portaudio19-dev xclip jq netcat-openbsd
```

### 2. Python Dependencies (Server Build Only)
To compile the server, you need the following Python environment.

**`requirements.txt`**
```text
cleantext
edge-tts
miniaudio
simpleaudio
setproctitle
nuitka
```

---

## 🛠️ Build & Setup

You will create two files in the same directory (e.g., `~/bin/`):
1.  `tts-server` (Compiled Python binary)
2.  `tts-client` (Bash script)

### Step 1: Compile the Server
The server handles the heavy lifting. We compile it using Nuitka to create a standalone binary.

**Note:** Adjust the `--include-data-dir` path to match your NLTK data location.

```bash
# Get path to nltk_data if you don't know it
python3 -c "import nltk; print(nltk.data.path[0])"

# Compile server.py
python3 -m nuitka --onefile \
   --lto=yes \
   --static-libpython=no \
   --plugin-enable=anti-bloat \
   --follow-imports \
   --include-module=_cffi_backend \
   --include-package-data=certifi \
   --include-data-dir=/home/dev/nltk_data=nltk_data \
   server.py \
   -o tts-server
```

### Step 2: Setup the Client
No compilation needed! Just rename `client.sh` and make it executable.

```bash
cp client.sh tts-client
chmod +x tts-client
```

### Step 3: Deployment
Move both files to a folder in your system `$PATH` so you can run them from anywhere.

```bash
mkdir -p ~/bin
mv tts-server ~/bin/
mv tts-client ~/bin/
# Ensure ~/bin is in your PATH, or reference full path in shortcuts
```

---

## 🚀 Usage

Since the client automatically starts the server, you just run the client.

- **Read from Primary Selection (Highlight)** - *Default behavior*
  ```bash
  tts-client
  ```

- **Read specific text**
  ```bash
  tts-client -t "Hello, this is a test sentence."
  ```

- **Stop playback immediately**
  ```bash
  tts-client -s
  ```

- **List available voices**
  ```bash
  tts-client -l
  ```

- **Change Voice**
  ```bash
  tts-client -v "en-GB-SoniaNeural"
  ```

---

## ⌨️ Setting Up Keyboard Shortcuts

Bind the script to **system-wide hotkeys** (e.g., in Linux Mint/Ubuntu Settings):

1.  **Read Selection**
    * **Command:** `/home/username/bin/tts-client`
    * **Key:** `Ctrl+Alt+Q`

2.  **Stop Reading**
    * **Command:** `/home/username/bin/tts-client -s`
    * **Key:** `Ctrl+Alt+E`

---

## 🔧 Troubleshooting

**Server won't start?**
The client suppresses server logs. To debug, try running the server manually in a terminal:
```bash
./tts-server
```
If it crashes, check for missing NLTK data or SSL certificate errors (common with Nuitka builds).

**Server stuck?**
If the server process gets stuck, you can force kill it:
```bash
pkill -f tts-server
```