#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import re
import subprocess
import logging
import io

import edge_tts
import soundfile as sf
import simpleaudio as sa

# --- Config ---
DEFAULT_VOICE = "en-US-EmmaNeural"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class TTSPlayer:
    def __init__(self, voice=DEFAULT_VOICE):
        self.voice = voice
        self.sentences = []

    def _get_clipboard_text(self):
        """Read primary selection from xclip"""
        try:
            text = (
                subprocess.check_output(["xclip", "-out", "-selection", "primary"])
                .decode("utf-8")
                .strip()
            )
            self.sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s]
        except Exception as e:
            logging.error(f"Error reading clipboard: {e}")
            self.sentences = []

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
        self._get_clipboard_text()
        if not self.sentences:
            logging.warning("No text found in clipboard.")
            return

        logging.info("Starting TTS playback...")

        # Pre-generate the first sentence
        prev_task = asyncio.create_task(self._synthesize_sentence(self.sentences[0]))
        prev_wave = await prev_task
        play_obj = prev_wave.play()

        for sentence in self.sentences[1:]:
            # Start generating next sentence in parallel
            next_task = asyncio.create_task(self._synthesize_sentence(sentence))

            # Wait for previous playback to finish
            play_obj.wait_done()

            # Wait for next sentence to finish generating
            next_wave = await next_task

            # Play next sentence
            play_obj = next_wave.play()

        # Wait for last sentence to finish
        play_obj.wait_done()
        logging.info("Playback finished.")


if __name__ == "__main__":
    player = TTSPlayer()
    asyncio.run(player.run())