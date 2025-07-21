#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A robust script to convert a text file into an audiobook,
with a resume feature and universal text cleaning.
"""

import asyncio
import edge_tts
import os
import sys
import subprocess
import argparse
import logging
import json
import signal
import atexit
import re
from pathlib import Path
from typing import List

# --- Setup Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Configuration ---
DEFAULT_VOICE = "en-US-EmmaNeural"
CHARS_PER_PAGE = 2500
MAX_RETRIES = 3
RETRY_DELAY_S = 5


class BookConverter:
    """Handles the logic for converting a text file to an audiobook."""

    def __init__(self, output_dir: Path, voice: str = None, book_path: Path = None, pages_per_file: int = None):
        self.output_dir = output_dir
        self.temp_dir = output_dir / "temp"
        self.state_file_path = output_dir / "conversion_state.json"
        
        self.book_path = book_path
        self.voice = voice
        self.pages_per_file = pages_per_file
        self.pages: List[str] = []
        self.next_page_index = 0
        self._cleaned_up = False

        def signal_handler(sig, frame):
            logging.warning(f"Interrupt signal ({signal.strsignal(sig)}) received. Shutting down gracefully.")
            self.cleanup()
            sys.exit(0)

        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _check_ffmpeg(self):
        """Checks if ffmpeg is installed and accessible."""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logging.error("ffmpeg not found. Please install ffmpeg and ensure it's in your system's PATH.")
            return False

    def _prepare_directories(self):
        """Creates the necessary output and temporary directories."""
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
    
    def cleanup(self):
        """Cleans up temporary files. Leaves state file for resume."""
        if self._cleaned_up:
            return
        logging.info("Running cleanup...")
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._cleaned_up = True
    
    def _save_state(self):
        """Saves the current conversion state to the JSON file."""
        state = {
            "book_path": str(self.book_path),
            "voice": self.voice,
            "pages_per_file": self.pages_per_file,
            "total_pages": len(self.pages),
            "next_page_index": self.next_page_index,
        }
        self.state_file_path.write_text(json.dumps(state, indent=4))

    def _load_state(self) -> bool:
        """Loads a previous conversion state from the JSON file."""
        if not self.state_file_path.exists():
            logging.error(f"No state file found at {self.state_file_path} to continue.")
            return False
        
        try:
            logging.info(f"Loading previous state from {self.state_file_path}")
            state = json.loads(self.state_file_path.read_text())
            self.book_path = Path(state["book_path"])
            self.voice = state["voice"]
            self.pages_per_file = state["pages_per_file"]
            self.next_page_index = state["next_page_index"]
            self._split_book_into_pages()
            return True
        except (KeyError, json.JSONDecodeError) as e:
            logging.error(f"State file is corrupt. Please start a new conversion. Error: {e}")
            return False

    def _clean_text(self, content: str) -> str:
        """A simple cleaner to remove unwanted characters and normalize whitespace."""
        logging.info("Cleaning book content...")
        
        # 1. Remove characters that are not letters, numbers, standard punctuation, or whitespace.
        # This keeps the original text content but removes obscure symbols.
        allowed_chars_pattern = r"[^a-zA-Z0-9\s.,?!'-]"
        cleaned_content = re.sub(allowed_chars_pattern, "", content)
        
        # 2. Normalize all whitespace (multiple spaces, newlines, tabs) into a single space.
        whitespace_pattern = r"\s+"
        normalized_content = re.sub(whitespace_pattern, " ", cleaned_content).strip()
        
        return normalized_content

    def _split_book_into_pages(self):
        """Reads the book, cleans the text, and splits it into pages."""
        try:
            logging.info(f"Reading book from: {self.book_path}")
            raw_content = self.book_path.read_text(encoding='utf-8')
            
            # Use the simple helper function to clean the text
            normalized_content = self._clean_text(raw_content)
            
            pages_list = []
            current_position = 0
            while current_position < len(normalized_content):
                end_position = min(current_position + CHARS_PER_PAGE, len(normalized_content))
                if end_position >= len(normalized_content):
                    pages_list.append(normalized_content[current_position:])
                    break
                
                best_break = -1
                for punc in ".!?":
                    best_break = max(best_break, normalized_content.rfind(punc, current_position, end_position))
                if best_break == -1:
                    best_break = max(best_break, normalized_content.rfind(' ', current_position, end_position))
                
                final_end = best_break + 1 if best_break != -1 else end_position
                pages_list.append(normalized_content[current_position:final_end])
                current_position = final_end
            
            self.pages = pages_list
            logging.info(f"Book split into {len(self.pages)} cleaned pages.")
            
        except FileNotFoundError:
            logging.error(f"Book file not found at: {self.book_path}")
            self.pages = []

    async def _synthesize_page(self, text: str, output_path: Path) -> bool:
        """Synthesizes a single page of text to an MP3 file with retries."""
        for attempt in range(MAX_RETRIES):
            try:
                communicate = edge_tts.Communicate(text=text, voice=self.voice)
                await communicate.save(str(output_path))
                return True
            except Exception as e:
                logging.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {output_path.name}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY_S)
        logging.error(f"All {MAX_RETRIES} attempts failed for {output_path.name}. Skipping.")
        return False

    def _merge_pages_to_part(self, part_index: int, page_files: List[Path]):
        """Merges a list of page MP3s into a single part file using ffmpeg."""
        part_filename = self.output_dir / f"part_{part_index:02d}.mp3"
        file_list_path = self.temp_dir / "filelist.txt"

        with open(file_list_path, "w", encoding='utf-8') as f:
            for page_file in page_files:
                f.write(f"file '{page_file.resolve()}'\n")
        
        logging.info(f"Merging {len(page_files)} pages into {part_filename.name}...")
        command = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(file_list_path), "-c", "copy", str(part_filename)]
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.error(f"ffmpeg failed for {part_filename.name}:\n{result.stderr}")
        else:
            logging.info(f"Successfully created {part_filename.name}")

    async def convert(self, continue_run=False):
        """Main execution flow for the conversion process."""
        if not self._check_ffmpeg(): return
        self._prepare_directories()

        if continue_run:
            if not self._load_state(): return
            logging.info(f"Resuming conversion from page {self.next_page_index + 1}/{len(self.pages)}")
        else:
            self._split_book_into_pages()
            if not self.pages: return
            self._save_state()

        current_part_page_files = []
        current_part_start_page = self.next_page_index
        
        for i in range(self.next_page_index, len(self.pages)):
            if (i - current_part_start_page) > 0 and (i - current_part_start_page) % self.pages_per_file == 0:
                part_index = (current_part_start_page // self.pages_per_file) + 1
                if current_part_page_files:
                    self._merge_pages_to_part(part_index, current_part_page_files)
                for f in current_part_page_files: f.unlink()
                current_part_page_files = []
                current_part_start_page = i

            page_text = self.pages[i]
            page_filename = self.temp_dir / f"page_{i:04d}.mp3"
            logging.info(f"Synthesizing page {i + 1}/{len(self.pages)}...")
            if await self._synthesize_page(page_text, page_filename):
                current_part_page_files.append(page_filename)
                
                self.next_page_index = i + 1
                self._save_state()

        if current_part_page_files:
            part_index = (current_part_start_page // self.pages_per_file) + 1
            self._merge_pages_to_part(part_index, current_part_page_files)
        for f in current_part_page_files: f.unlink()
        
        logging.info("--- Audiobook conversion complete! ---")
        self.state_file_path.unlink(missing_ok=True)
        (self.temp_dir / "filelist.txt").unlink(missing_ok=True)
        try:
            self.temp_dir.rmdir()
        except OSError as e:
            logging.warning(f"Could not remove temp directory {self.temp_dir}. It may not be empty. Error: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert a text book to an audiobook with resume capability.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-b", "--book", type=Path, help="Path to the input text file for a NEW conversion.")
    group.add_argument("-c", "--continue-run", action="store_true", help="Continue the last interrupted conversion.")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help=f"The voice to use for synthesis.\nDefault: {DEFAULT_VOICE}")
    parser.add_argument("-p", "--pages", type=int, default=10, help="Number of pages to combine into a single audio file.\nDefault: 10")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("audio_book"), help="The directory to store the final audiobook files.\nDefault: ./audio_book/")
    
    args = parser.parse_args()

    if args.continue_run:
        converter = BookConverter(output_dir=args.output_dir)
        run_task = converter.convert(continue_run=True)
    else:
        converter = BookConverter(
            book_path=args.book,
            voice=args.voice,
            pages_per_file=args.pages,
            output_dir=args.output_dir
        )
        run_task = converter.convert(continue_run=False)
    
    try:
        asyncio.run(run_task)
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. State saved for resume.")
    except Exception as e:
        logging.critical(f"A critical error occurred: {e}")

if __name__ == "__main__":
    main()