#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import re
import subprocess
import sys
import tempfile
import atexit
import logging
from pathlib import Path
import edge_tts
import sounddevice as sd
import soundfile as sf

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

DEFAULT_VOICE = "en-US-EmmaNeural"

class TTSPlayer:
    def __init__(self, voice=DEFAULT_VOICE):
        self.voice = voice
        self.sentences = []

    def _get_clipboard_text(self):
        try:
            text = subprocess.check_output(
                ['xclip', '-out', '-selection', 'primary']
            ).decode('utf-8').strip()
            self.sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if s]
        except Exception as e:
            logging.error(f"Error reading clipboard: {e}")
            self.sentences = []

    async def _synthesize_chunk(self, text: str, output_path: Path):
        """Generate WAV chunk from edge-tts"""
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))

    async def run(self):
        self._get_clipboard_text()
        if not self.sentences:
            logging.warning("No text found in clipboard.")
            return

        logging.info("Starting TTS playback...")
        prev_task = None
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            for i, sentence in enumerate(self.sentences):
                chunk_path = tmpdir / f"chunk_{i}.wav"

                # Start synthesis for this chunk
                task = asyncio.create_task(self._synthesize_chunk(sentence, chunk_path))

                # Wait for previous chunk to finish, then play
                if prev_task:
                    await prev_task
                    self._play_wav(prev_path)

                prev_path = chunk_path
                prev_task = task

            # Play last chunk
            if prev_task:
                await prev_task
                self._play_wav(prev_path)

        logging.info("Playback finished.")

    def _play_wav(self, path: Path):
        """Stream WAV file via sounddevice"""
        data, samplerate = sf.read(str(path), dtype='float32')
        sd.play(data, samplerate)
        sd.wait()  # Wait for playback to finish

if __name__ == "__main__":
    player = TTSPlayer()
    asyncio.run(player.run())