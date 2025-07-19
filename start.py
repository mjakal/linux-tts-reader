# Requirements
# pip install edge-tts
# sudo apt install xclip mpv
# Run it: python3 start.py en-US-EmmaNeural

import asyncio
import edge_tts
import os
import sys
import subprocess
import tempfile
import re
import atexit
import shutil
import signal
from concurrent.futures import ThreadPoolExecutor

# === PID File for External Stop Control ===
pid_file = "/tmp/edge_tts_reader.pid"
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

mpv_processes = []
temp_dir = tempfile.mkdtemp()

# === Cleanup Resources on Exit ===
def cleanup():
    print("\nCleaning up...")
    for proc in mpv_processes:
        try:
            proc.terminate()
        except Exception:
            pass
    shutil.rmtree(temp_dir, ignore_errors=True)
    if os.path.exists(pid_file):
        os.remove(pid_file)

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))

# === Get voice id from script argument ===
voice_id = sys.argv[1] if len(sys.argv) > 1 else "en-US-EmmaNeural"

# === Get Clipboard Text ===
selected_text = subprocess.check_output(
    ['xclip', '-out', '-selection', 'primary']
).decode('utf-8').strip()

# === Split Text into Sentences ===
def split_into_sentences(text):
    return re.split(r'(?<=[.!?]) +', text.strip())

sentences = split_into_sentences(selected_text)

# === Async TTS + Playback ===
async def synthesize_and_play(sentences, voice_id):
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor()
    tasks = []

    async def synthesize(index, sentence):
        output_path = os.path.join(temp_dir, f"chunk_{index}.mp3")
        communicate = edge_tts.Communicate(text=sentence, voice=voice_id)
        await communicate.save(output_path)
        return index, output_path

    # Synthesize all sentences asynchronously
    for idx, sentence in enumerate(sentences):
        if sentence.strip():
            tasks.append(synthesize(idx, sentence))

    results = await asyncio.gather(*tasks)
    sorted_results = sorted(results, key=lambda x: x[0])

    # Play each chunk using mpv (sequentially)
    for _, path in sorted_results:
        print(f"Playing: {os.path.basename(path)}")
        proc = subprocess.Popen([
            "mpv", "--no-terminal", "--really-quiet", path
        ])
        mpv_processes.append(proc)
        proc.wait()

# === Run Main ===
asyncio.run(synthesize_and_play(sentences, voice_id))

