#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A self-contained, real-time text-to-speech script using edge-tts and mpv.
Can be started, stopped, and managed with command-line arguments.
"""

import asyncio
import edge_tts
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import atexit
import argparse
import logging
from pathlib import Path

# --- Setup Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Configuration ---
MPV_SOCKET_PATH = Path("/tmp/mpv_socket")
DEFAULT_VOICE = "en-US-EmmaNeural"


class TTSPlayer:
    def __init__(self, voice: str):
        self.voice = voice
        self.temp_dir = Path(tempfile.mkdtemp(prefix="tts_player_"))
        self.mpv_process: subprocess.Popen | None = None
        self.sentences: list[str] = []
        self._cleaned_up = False

        def signal_handler(sig, frame):
            logging.info(f"Signal {signal.strsignal(sig)} received. Shutting down.")
            self.cleanup()
            sys.exit(0)

        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _get_clipboard_text(self):
        try:
            text = subprocess.check_output(
                ['xclip', '-out', '-selection', 'primary']
            ).decode('utf-8').strip()
            self.sentences = [
                s for s in re.split(r'(?<=[.!?])\s+', text) if s
            ]
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logging.error(f"Error getting text from xclip: {e}")
            self.sentences = []

    def cleanup(self):
        if self._cleaned_up:
            return
        logging.info("Cleaning up resources...")
        if self.mpv_process and self.mpv_process.poll() is None:
            logging.info(f"Terminating mpv process (PID: {self.mpv_process.pid})")
            try:
                self.mpv_process.terminate()
                self.mpv_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mpv_process.kill()
                self.mpv_process.wait()
            except Exception as e:
                logging.error(f"Error during mpv cleanup: {e}")
        
        MPV_SOCKET_PATH.unlink(missing_ok=True)
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._cleaned_up = True

    async def _synthesize_chunk(self, text: str, output_path: Path):
        try:
            communicate = edge_tts.Communicate(text=text, voice=self.voice)
            await communicate.save(str(output_path))
            return True
        except Exception as e:
            logging.error(f"Failed to synthesize chunk for path {output_path}: {e}")
            return False

    async def run(self):
        self._get_clipboard_text()
        if not self.sentences:
            logging.warning("No sentences to process. Exiting.")
            return

        loop = asyncio.get_running_loop()
        
        first_chunk_path = self.temp_dir / "chunk_0.mp3"
        if not await self._synthesize_chunk(self.sentences[0], first_chunk_path):
            logging.error("Failed to synthesize the first chunk. Aborting.")
            return
        
        logging.info("First chunk synthesized. Launching mpv...")
        MPV_SOCKET_PATH.unlink(missing_ok=True)
        self.mpv_process = subprocess.Popen([
            "mpv", "--no-terminal", "--quiet", str(first_chunk_path),
            f"--input-ipc-server={MPV_SOCKET_PATH}"
        ])

        if len(self.sentences) > 1:
            await self._stream_remaining_chunks(self.sentences[1:], loop)
        
        logging.info("All chunks queued. Waiting for mpv to finish playback...")
        if self.mpv_process:
            await loop.run_in_executor(None, self.mpv_process.wait)
        logging.info("Playback finished and mpv has exited.")

    async def _stream_remaining_chunks(self, sentences: list, loop):
        for _ in range(50):
            if MPV_SOCKET_PATH.exists():
                break
            await asyncio.sleep(0.1)
        else:
            logging.error("MPV socket was not created in time by running instance.")
            return
        
        try:
            ipc_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            ipc_socket.setblocking(False)
            await loop.sock_connect(ipc_socket, str(MPV_SOCKET_PATH))
        except Exception as e:
            logging.error(f"Could not connect to mpv socket: {e}")
            return

        total_chunks = len(self.sentences)
        for i, sentence in enumerate(sentences, start=1):
            chunk_path = self.temp_dir / f"chunk_{i}.mp3"
            if await self._synthesize_chunk(sentence, chunk_path):
                command = {"command": ["loadfile", str(chunk_path), "append"]}
                payload = (json.dumps(command) + "\n").encode()
                await loop.sock_sendall(ipc_socket, payload)
                logging.info(f"Appended chunk {i + 1}/{total_chunks}")
        ipc_socket.close()

async def list_voices():
    """Lists all available voices from edge-tts."""
    print("Available voices:")
    voices = await edge_tts.list_voices()
    for voice in sorted(voices, key=lambda v: v["ShortName"]):
        print(f"  - {voice['ShortName']:<20} {voice['Gender']:<8} {voice['Locale']}")

def stop_existing_instance():
    """Finds and stops any running instance of this script using pkill."""
    script_name = os.path.basename(__file__)
    command = ["pkill", "-f", f"python.*{script_name}"]
    
    logging.info(f"Attempting to stop all instances of '{script_name}'...")
    result = subprocess.run(command)
    
    if result.returncode == 0:
        logging.info("Success: Stop signal sent.")
    else:
        logging.info("No running reader process found.")

def main():
    """Main entry point with argument parsing to control behavior."""
    parser = argparse.ArgumentParser(
        description="A tool to read clipboard text aloud, list voices, or stop a running instance.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # Use a mutually exclusive group for actions that don't start the player
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "-s", "--stop",
        action="store_true",
        help="Stop any running instance of the reader script."
    )
    action_group.add_argument(
        "-l", "--list-voices",
        action="store_true",
        help="List all available voices and exit."
    )
    # The voice argument is for the default "run" action
    parser.add_argument(
        "-v", "--voice",
        default=DEFAULT_VOICE,
        help=f"The voice to use for synthesis.\nDefault: {DEFAULT_VOICE}"
    )
    args = parser.parse_args()

    # --- Main Control Flow ---
    if args.stop:
        stop_existing_instance()
    elif args.list_voices:
        asyncio.run(list_voices())
    else:
        # Default action: run the TTS player
        player = TTSPlayer(voice=args.voice)
        try:
            logging.info(f"Starting TTS player with voice: {args.voice}")
            asyncio.run(player.run())
        except Exception as e:
            logging.critical(f"A critical error occurred: {e}")
        finally:
            logging.info("Script execution finished.")

if __name__ == "__main__":
    main()