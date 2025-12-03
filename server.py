#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# server.py

import asyncio
import json
import logging
import os
import re
import signal
import setproctitle
import edge_tts
import miniaudio
from miniaudio import SampleFormat
import simpleaudio as sa
import cleantext

# --- Config ---
SOCKET_PATH = "/tmp/enge_tts.sock"
PROCESS_NAME = "enge-tts-server"
DEFAULT_VOICE = "en-US-EmmaNeural"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - SERVER - %(message)s",
    datefmt="%H:%M:%S",
)

class TTSPlayer:
    def __init__(self, text: str, voice: str):
        self.voice = voice
        self.sentences = self._split_and_merge_sentences(text)
        self._current_play_obj = None
        self._stop_event = asyncio.Event()

    def _split_and_merge_sentences(self, text: str, min_words_to_merge: int = 6):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if not sentences: return []
        merged = []
        i = 0
        while i < len(sentences):
            curr = sentences[i].strip()
            if not curr:
                i += 1; continue
            if len(curr.split()) < min_words_to_merge and (i + 1) < len(sentences):
                next_s = sentences[i + 1].strip()
                if next_s: merged.append(curr + " " + next_s); i += 2
                else: merged.append(curr); i += 2
            else:
                merged.append(curr); i += 1
        return [s for s in merged if s]

    async def _synthesize_sentence(self, sentence: str) -> sa.WaveObject:
        communicate = edge_tts.Communicate(sentence, self.voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        audio_data = miniaudio.decode(audio_bytes, output_format=SampleFormat.SIGNED16)
        return sa.WaveObject(
            audio_data.samples.tobytes(),
            num_channels=audio_data.nchannels,
            bytes_per_sample=audio_data.sample_width,
            sample_rate=audio_data.sample_rate,
        )

    def stop(self):
        """Signal the player to stop."""
        self._stop_event.set()
        if self._current_play_obj and self._current_play_obj.is_playing():
            self._current_play_obj.stop()

    async def run(self):
        if not self.sentences: return
        loop = asyncio.get_running_loop()
        
        try:
            # Pre-buffer first sentence
            current_wave = await self._synthesize_sentence(self.sentences[0])
            next_task = None
            
            if len(self.sentences) > 1:
                next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[1]))

            self._current_play_obj = current_wave.play()
            
            for i in range(1, len(self.sentences)):
                if self._stop_event.is_set(): break
                
                # Wait for current audio to finish
                await loop.run_in_executor(None, self._current_play_obj.wait_done)
                
                if self._stop_event.is_set(): break

                current_wave = await next_task
                if i + 1 < len(self.sentences):
                    next_task = asyncio.create_task(self._synthesize_sentence(self.sentences[i + 1]))
                
                self._current_play_obj = current_wave.play()

            if self._current_play_obj and not self._stop_event.is_set():
                await loop.run_in_executor(None, self._current_play_obj.wait_done)

        except Exception as e:
            logging.error(f"Playback error: {e}")
        finally:
            logging.info("Playback finished or stopped.")

class TTSServer:
    def __init__(self):
        self.current_player_task = None
        self.current_player = None

    def clean_text(self, text):
        return cleantext.clean(
            text, extra_spaces=True, lowercase=False, numbers=False, punct=False, reg=r'\[.*?\]'
        )

    async def handle_client(self, reader, writer):
        data = await reader.read(100000) # Read up to 100KB
        message = data.decode()
        addr = writer.get_extra_info('peername')
        logging.info(f"Received request from {addr}")

        try:
            request = json.loads(message)
            command = request.get('command')

            if command == 'stop':
                await self.stop_playback()
                response = "Stopped"
            
            elif command == 'read':
                # 1. Stop existing
                await self.stop_playback()
                
                # 2. Process new
                text = request.get('text', '')
                voice = request.get('voice', DEFAULT_VOICE)
                clean = request.get('clean', True)
                
                if clean:
                    text = self.clean_text(text)
                
                # 3. Start new
                self.current_player = TTSPlayer(text, voice)
                self.current_player_task = asyncio.create_task(self.current_player.run())
                response = "Reading started"

            else:
                response = "Unknown command"

        except json.JSONDecodeError:
            response = "Invalid JSON"
        except Exception as e:
            logging.error(f"Error handling request: {e}")
            response = f"Server Error: {str(e)}"

        logging.info(f"Response: {response}")
        try:
            writer.write(response.encode())
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            logging.warning("Client disconnected before response was fully sent (not critical).")
        except Exception as e:
            logging.error(f"Network write error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass # Socket already dead, ignore        

    async def stop_playback(self):
        if self.current_player:
            self.current_player.stop()
        if self.current_player_task:
            self.current_player_task.cancel()
            try:
                await self.current_player_task
            except asyncio.CancelledError:
                pass
        self.current_player = None
        self.current_player_task = None

    async def run_server(self):
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

        server = await asyncio.start_unix_server(self.handle_client, path=SOCKET_PATH)
        logging.info(f"Serving on {SOCKET_PATH}")

        async with server:
            await server.serve_forever()

if __name__ == "__main__":
    setproctitle.setproctitle(PROCESS_NAME)
    # Handle Ctrl+C gracefully
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tts_server = TTSServer()
    try:
        loop.run_until_complete(tts_server.run_server())
    except KeyboardInterrupt:
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
