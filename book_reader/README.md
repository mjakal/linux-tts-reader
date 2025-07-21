# Audiobook Converter

A robust command-line tool to convert text files (like books) into high-quality audiobooks using Microsoft Edge's Text-to-Speech service. The script is designed to handle large files, interruptions, and provides flexible options for a smooth conversion process.

## Features

* **Text-to-Audio Conversion**: Utilizes the high-quality voices from Microsoft Edge's TTS service to generate natural-sounding audio.
* **Intelligent Text Splitting**: The script doesn't just cut text by character count; it intelligently splits the book into "pages" at natural sentence endings (`.`, `!`, `?`) for better audio flow.
* **Universal Text Cleaning**: Before synthesis, the script automatically cleans the source text by removing obscure special characters and normalizing inconsistent whitespace, improving the quality of the TTS output for any language.
* **Resume Interrupted Sessions**: If the script is stopped or fails, it saves its progress. You can easily resume the conversion exactly where it left off, saving significant time and effort on large books.
* **Audio Part Merging**: Individual audio pages are automatically merged into larger, chapter-like `part_XX.mp3` files using `ffmpeg`, making the final audiobook easy to navigate.
* **Robust Retry Logic**: Includes a built-in retry mechanism to automatically handle temporary network errors during the synthesis process, ensuring the conversion doesn't fail unnecessarily.
* **Customizable Options**: Easily configure the TTS voice, the number of pages per audio file, and the output directory directly from the command line.

## Requirements

To use this script, you will need the following installed on your system:

1.  **Python 3.8+**
2.  **edge-tts**: The Python library that communicates with the TTS service.
3.  **ffmpeg**: A powerful multimedia framework required for merging audio files.

## Installation

1.  **Install Python**: Ensure you have Python 3.8 or newer installed.

2.  **Install `edge-tts`**: Open your terminal and install the library using pip.
    ```bash
    pip install edge-tts
    ```

3.  **Install `ffmpeg`**:
    * **On Debian/Ubuntu/Mint:**
        ```bash
        sudo apt update && sudo apt install ffmpeg
        ```
    * **On Fedora/CentOS/RHEL:**
        ```bash
        sudo dnf install ffmpeg
        ```
    * **On Arch Linux/Manjaro:**
        ```bash
        sudo pacman -S ffmpeg
        ```
    * **On macOS (using Homebrew):**
        ```bash
        brew install ffmpeg
        ```

## Usage

Clone the repo and run the script from your terminal.

### Starting a New Conversion

This is the most common use case. You must provide the path to your book file.

**Basic Command:**
This command will convert `my_book.txt` using the default voice (`en-US-EmmaNeural`) and group 10 pages into each audio part.
```bash
python3 book_reader.py -b my_book.txt
```

**With Custom Options:**
This command uses a specific Croatian voice, sets 15 pages per part, and saves the output to a directory named `my_croatian_audiobook`.
```bash
python3 book_reader.py -b my_book.txt -v hr-HR-GabrijelaNeural -p 15 -o my_croatian_audiobook
```

### Continuing an Interrupted Conversion

If the script was stopped for any reason, you can easily resume it. The script will automatically load its last saved state from the output directory.

**Resume Command:**
You only need to specify the output directory where the conversion was started.
```bash
python3 book_reader.py -c -o audio_book
```
*(Note: If you used the default output directory, `-o audio_book` is sufficient. If you used a custom one, specify it here.)*

## Command-Line Arguments

| Argument          | Short | Description                                                                 | Required                               |
| ----------------- | ----- | --------------------------------------------------------------------------- | -------------------------------------- |
| `--book`          | `-b`  | Path to the input text file for a **new** conversion.                       | Yes (for new runs)                     |
| `--continue-run`  | `-c`  | Continue the last interrupted conversion from the specified output directory. | Yes (for resuming)                     |
| `--voice`         | `-v`  | The `edge-tts` voice to use for synthesis.                                  | No (defaults to `en-US-EmmaNeural`)    |
| `--pages`         | `-p`  | The number of pages to combine into a single audio file.                    | No (defaults to `10`)                  |
| `--output-dir`    | `-o`  | The directory to store the final audiobook files and state.                 | No (defaults to `./audio_book/`)       |
