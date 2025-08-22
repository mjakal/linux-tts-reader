#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import re
import subprocess
import logging
import argparse
import sys
import os

import edge_tts
import miniaudio
from miniaudio import SampleFormat
import simpleaudio as sa
import cleantext
import setproctitle

# --- Config ---
DEFAULT_VOICE = "en-US-EmmaNeural"
PROCESS_NAME = "tts-reader-service"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

class TTSPlayer:
    def __init__(self, text: str, voice=DEFAULT_VOICE):
        self.voice = voice
        # --- Use the new intelligent chunking method ---
        self.sentences = self._split_into_chunks(text)
        self._current_play_obj = None

    def _split_into_chunks(self, text: str, target_words: int = 20, max_words: int = 35):
        """Splits text into manageable chunks for smoother TTS playback."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []

        for sentence in sentences:
            words = sentence.split()
            if not words:
                continue

            if len(words) <= max_words:
                chunks.append(sentence)
                continue

            current_pos = 0
            while current_pos < len(words):
                end_pos = min(current_pos + target_words, len(words))
                break_pos = -1
                
                # Look for punctuation backwards from the end position
                for i in range(min(end_pos, len(words) - 1), current_pos, -1):
                    if words[i].endswith((',', ';', ':', '—')):
                        break_pos = i + 1
                        break
                
                if break_pos == -1:
                    break_pos = end_pos
                
                chunk_words = words[current_pos:break_pos]
                chunks.append(" ".join(chunk_words))
                current_pos = break_pos
        
        return [c.strip() for c in chunks if c.strip()]

    async def _synthesize_sentence(self, sentence: str) -> sa.WaveObject:
        """Synthesizes and decodes audio, returning a simpleaudio object."""
        communicate = edge_tts.Communicate(sentence, self.voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        audio_data = miniaudio.decode(
            audio_bytes,
            output_format=SampleFormat.SIGNED16
        )
        
        return sa.WaveObject(
            audio_data.samples.tobytes(),
            num_channels=audio_data.nchannels,
            bytes_per_sample=audio_data.sample_width,
            sample_rate=audio_data.sample_rate,
        )

    async def run(self):
        if not self.sentences:
            logging.warning("No sentences to process.")
            return

        logging.info(f"Starting TTS playback with voice: {self.voice}")
        loop = asyncio.get_running_loop()
        try:
            current_wave = await self._synthesize_sentence(self.sentences[0])

            next_task = None
            if len(self.sentences) > 1:
                next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[1]))

            logging.info(f"Reading: '{self.sentences[0]}'")
            self._current_play_obj = current_wave.play()

            for i in range(1, len(self.sentences)):
                await loop.run_in_executor(None, self._current_play_obj.wait_done)
                current_wave = await next_task
                if i + 1 < len(self.sentences):
                    next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[i + 1]))
                logging.info(f"Reading: '{self.sentences[i]}'")
                self._current_play_obj = current_wave.play()

            if self._current_play_obj:
                await loop.run_in_executor(None, self._current_play_obj.wait_done)

            logging.info("Playback finished.")

        except (asyncio.CancelledError, KeyboardInterrupt):
            logging.info("Playback interrupted.")
            if self._current_play_obj and self._current_play_obj.is_playing():
                self._current_play_obj.stop()


async def list_voices():
    """Lists all available voices from the edge-tts library."""
    print("Fetching available voices...")
    try:
        voices = await edge_tts.list_voices()
        for voice in sorted(voices, key=lambda v: v['ShortName']):
            print(f"  - {voice['ShortName']:<20} | Gender: {voice['Gender']}")
    except Exception as e:
        logging.error(f"Failed to list voices: {e}")

def stop_existing_instance():
    """Finds and stops any running instance of this script by its unique process name."""
    command = ["pkill", "-f", PROCESS_NAME]
    logging.info(f"Attempting to stop all running instances of '{PROCESS_NAME}'...")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        logging.info("Success: A running instance was stopped.")
    else:
        logging.info("No running instance found.")


def main():
    """Main entry point with argument parsing to control behavior."""
    parser = argparse.ArgumentParser(
        description="A tool to read text aloud using Edge TTS.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "-s", "--stop", action="store_true",
        help="Stop any running instance of this script and exit."
    )
    action_group.add_argument(
        "-l", "--list-voices", action="store_true",
        help="List all available voices and exit."
    )

    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "-t", "--text", type=str,
        help="Provide the text to be read directly."
    )
    source_group.add_argument(
        "-c", "--clipboard", action="store_true",
        help="Read text from the clipboard (default behavior)."
    )
    
    parser.add_argument(
        "-v", "--voice", default=DEFAULT_VOICE,
        help=f"The voice to use for speech synthesis.\nDefault: {DEFAULT_VOICE}"
    )
    parser.add_argument(
        "--no-clean", action="store_true",
        help="Disable the text cleaning process."
    )
    
    args = parser.parse_args()

    if args.stop:
        stop_existing_instance()
        sys.exit(0)
        
    if args.list_voices:
        asyncio.run(list_voices())
        sys.exit(0)

    setproctitle.setproctitle(PROCESS_NAME)

    text_to_read = ""
    if args.text:
        logging.info("Reading text provided via -t argument.")
        text_to_read = args.text
    else:
        logging.info("Reading text from clipboard.")
        try:
            text_to_read = (
                subprocess.check_output(["xclip", "-out", "-selection", "primary"])
                .decode("utf-8")
                .strip()
            )
        except FileNotFoundError:
            logging.error("`xclip` command not found. Please install it to use clipboard features.")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Could not read from clipboard: {e}")
            sys.exit(1)

    if not text_to_read:
        logging.warning("No text to read. Exiting.")
        sys.exit(0)
    
    if not args.no_clean:
        logging.info("Cleaning text...")
        cleaned_text = cleantext.clean(
            text_to_read,
            extra_spaces=True,
            lowercase=False,
            numbers=False,
            punct=False,
            reg=r'\[.*?\]',
        )
        text_to_read = " ".join(cleaned_text.split())
        logging.info("Text cleaned successfully.")
        
    player = TTSPlayer(text=text_to_read, voice=args.voice)
    try:
        asyncio.run(player.run())
    except KeyboardInterrupt:
        logging.info("Exited by user.")

if __name__ == "__main__":
    main()