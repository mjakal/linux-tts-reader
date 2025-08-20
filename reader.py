#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import re
import subprocess
import logging
import io
import argparse
import sys
import os

import edge_tts
import soundfile as sf
import simpleaudio as sa
import cleantext

# --- Config ---
DEFAULT_VOICE = "en-US-EmmaNeural"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class TTSPlayer:
    def __init__(self, text: str, voice=DEFAULT_VOICE):
        self.voice = voice
        if text:
            # Split text into sentences. This regex is better at handling various sentence endings.
            self.sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        else:
            self.sentences = []
        self._current_play_obj = None

    async def _synthesize_sentence(self, sentence: str) -> sa.WaveObject:
        """Generate WAV for a sentence in memory and return WaveObject"""
        communicate = edge_tts.Communicate(sentence, self.voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        buffer = io.BytesIO(audio_bytes)
        data, samplerate = sf.read(buffer, dtype="int16")
        raw_bytes = data.tobytes()
        return sa.WaveObject(
            raw_bytes,
            num_channels=data.shape[1] if len(data.shape) > 1 else 1,
            bytes_per_sample=2,
            sample_rate=samplerate,
        )

    async def run(self):
        if not self.sentences:
            logging.warning("No sentences to process.")
            return

        logging.info(f"Starting TTS playback with voice: {self.voice}")
        try:
            prev_task = asyncio.create_task(self._synthesize_sentence(self.sentences[0]))
            prev_wave = await prev_task
            self._current_play_obj = prev_wave.play()

            for sentence in self.sentences[1:]:
                next_task = asyncio.create_task(self._synthesize_sentence(sentence))
                self._current_play_obj.wait_done()
                next_wave = await next_task
                self._current_play_obj = next_wave.play()

            self._current_play_obj.wait_done()
            logging.info("Playback finished.")
        except asyncio.CancelledError:
            logging.info("Playback cancelled.")
            if self._current_play_obj:
                self._current_play_obj.stop()
        except KeyboardInterrupt:
            logging.info("Interrupted by user.")
            if self._current_play_obj:
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
    """Finds and stops any running instance of this script using pkill."""
    script_name = os.path.basename(__file__)
    command = ["pkill", "-f", f"python.*{script_name}"]
    logging.info(f"Attempting to stop all running instances of '{script_name}'...")
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
    # --- ADDED: Argument to disable cleaning ---
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
    
    # --- ADDED: Text cleaning step ---
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
        # The clean function can sometimes strip all whitespace, so we re-join lines.
        text_to_read = " ".join(cleaned_text.split())
        logging.info("Text cleaned successfully.")
        
    player = TTSPlayer(text=text_to_read, voice=args.voice)
    try:
        asyncio.run(player.run())
    except KeyboardInterrupt:
        logging.info("Exited by user.")

if __name__ == "__main__":
    main()