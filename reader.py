#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A self-contained, real-time text-to-speech script using the edge-tts command-line tool and mpv.
Can be started, stopped, and managed with command-line arguments.
Relies on pipx for edge-tts installation.
"""

import asyncio
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
        self.mpv_process: asyncio.subprocess.Process | None = None
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
        if self.mpv_process and self.mpv_process.returncode is None:
            logging.info(f"Terminating mpv process (PID: {self.mpv_process.pid})")
            try:
                self.mpv_process.terminate()
            except Exception as e:
                logging.error(f"Error during mpv cleanup: {e}")
        
        MPV_SOCKET_PATH.unlink(missing_ok=True)
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self._cleaned_up = True

    async def _synthesize_chunk(self, text: str, output_path: Path):
        """Synthesizes a text chunk using the edge-tts command-line tool."""
        command = [
            "edge-tts",
            "--voice", self.voice,
            "--text", text,
            "--write-media", str(output_path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logging.error(f"edge-tts failed for chunk '{text[:20]}...': {stderr.decode()}")
                return False
            return True
        except FileNotFoundError:
            logging.error("The 'edge-tts' command was not found. Is it installed with pipx and in your PATH?")
            # We exit here because the script cannot function without edge-tts
            sys.exit(1)
        except Exception as e:
            logging.error(f"Failed to synthesize chunk with subprocess for path {output_path}: {e}")
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
        self.mpv_process = await asyncio.create_subprocess_exec(
            "mpv",
            "--no-terminal",
            "--really-quiet",
            "--no-audio-display",
            "--no-terminal",
            str(first_chunk_path),
            f"--input-ipc-server={MPV_SOCKET_PATH}"
        )

        if len(self.sentences) > 1:
            await self._stream_remaining_chunks(self.sentences[1:], loop)
        
        logging.info("All chunks queued. Waiting for mpv to finish playback...")
        if self.mpv_process:
            await self.mpv_process.wait()
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
            reader, writer = await asyncio.open_unix_connection(str(MPV_SOCKET_PATH))
        except Exception as e:
            logging.error(f"Could not connect to mpv socket: {e}")
            return

        total_chunks = len(self.sentences)
        for i, sentence in enumerate(sentences, start=1):
            chunk_path = self.temp_dir / f"chunk_{i}.mp3"
            if await self._synthesize_chunk(sentence, chunk_path):
                command = {"command": ["loadfile", str(chunk_path), "append"]}
                payload = (json.dumps(command) + "\n").encode()
                writer.write(payload)
                await writer.drain()
                logging.info(f"Appended chunk {i + 1}/{total_chunks}")
        writer.close()
        await writer.wait_closed()

async def list_voices():
    """Lists all available voices by calling the edge-tts command."""
    print("Available voices (via 'edge-tts --list-voices'):")
    try:
        process = await asyncio.create_subprocess_exec(
            "edge-tts", "--list-voices",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logging.error(f"Failed to list voices: {stderr.decode()}")
            return
        print(stdout.decode().strip())
    except FileNotFoundError:
        logging.error("The 'edge-tts' command was not found. Is it installed with pipx and in your PATH?")

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

def check_dependencies():
    """Checks if required command-line tools are installed and in the PATH."""
    dependencies = ["mpv", "xclip", "edge-tts", "pkill"]
    missing = [cmd for cmd in dependencies if not shutil.which(cmd)]
    if missing:
        logging.critical(f"Missing required command-line tools: {', '.join(missing)}")
        logging.critical("Please install them. 'edge-tts' should be installed via 'pipx'.")
        sys.exit(1)

def main():
    """Main entry point with argument parsing to control behavior."""
    parser = argparse.ArgumentParser(
        description="A tool to read clipboard text aloud, list voices, or stop a running instance.",
        formatter_class=argparse.RawTextHelpFormatter
    )
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
    parser.add_argument(
        "-v", "--voice",
        default=DEFAULT_VOICE,
        help=f"The voice to use for synthesis.\nDefault: {DEFAULT_VOICE}"
    )
    args = parser.parse_args()

    # --- Main Control Flow ---
    check_dependencies()
    if args.stop:
        stop_existing_instance()
    elif args.list_voices:
        asyncio.run(list_voices())
    else:
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