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
import json
import socket

# === Config & State ===
pid_file = "/tmp/edge_tts_reader.pid"
mpv_socket_path = "/tmp/mpv_socket"
temp_dir = tempfile.mkdtemp()
mpv_process = None

# === Save PID ===
with open(pid_file, "w") as f:
    f.write(str(os.getpid()))

# === Cleanup Function ===
def cleanup():
    global mpv_process
    print("Cleaning up...")
    if mpv_process:
        try:
            mpv_process.terminate()
            mpv_process.wait(timeout=5)
        except Exception:
            try:
                mpv_process.kill()
                mpv_process.wait()
            except Exception:
                pass
    if os.path.exists(mpv_socket_path):
        os.remove(mpv_socket_path)
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(pid_file):
        os.remove(pid_file)

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))

# === Voice Selection ===
voice_id = sys.argv[1] if len(sys.argv) > 1 else "en-US-EmmaNeural"

# === Clipboard Input ===
selected_text = subprocess.check_output(['xclip', '-out', '-selection', 'primary']).decode('utf-8').strip()

# === Sentence Splitting ===
def split_into_sentences(text):
    return re.split(r'(?<=[.!?]) +', text.strip())

sentences = [s for s in split_into_sentences(selected_text) if s.strip()]

# === MPV IPC Helpers ===
async def send_ipc_command(sock, command_dict):
    command_str = json.dumps(command_dict) + "\n"
    await asyncio.get_event_loop().sock_sendall(sock, command_str.encode())

async def listen_until_done(sock, total_chunks):
    last_played_index = -1
    while True:
        try:
            data = await asyncio.get_event_loop().sock_recv(sock, 4096)
        except ConnectionResetError:
            return

        for line in data.splitlines():
            try:
                msg = json.loads(line.decode() if isinstance(line, bytes) else line)
                if msg.get("event") == "property-change" and msg.get("name") == "playlist-pos":
                    last_played_index = msg.get("data", last_played_index)
                elif msg.get("event") == "end-file":
                    if last_played_index == total_chunks - 1:
                        return
            except Exception:
                continue

# === Main Async Flow ===
async def synthesize_and_play(sentences, voice_id):
    global mpv_process
    loop = asyncio.get_event_loop()
    audio_paths = [None] * len(sentences)
    ready_events = [asyncio.Event() for _ in sentences]

    # Launch mpv
    if os.path.exists(mpv_socket_path):
        os.remove(mpv_socket_path)

    mpv_process = subprocess.Popen([
        "mpv",
        "--no-terminal",
        "--quiet",
        "--idle=yes",
        f"--input-ipc-server={mpv_socket_path}"
    ])

    # Wait for socket
    for _ in range(50):
        if os.path.exists(mpv_socket_path):
            break
        await asyncio.sleep(0.1)
    else:
        print("Error: MPV socket not created.")
        return

    # Connect to socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.setblocking(False)
    await loop.sock_connect(sock, mpv_socket_path)

    # Monitor playlist position
    await send_ipc_command(sock, {
        "command": ["observe_property", 1, "playlist-pos"]
    })

    # Start synthesis
    async def synth(index, text):
        path = os.path.join(temp_dir, f"chunk_{index}.mp3")
        communicate = edge_tts.Communicate(text=text, voice=voice_id)
        await communicate.save(path)
        audio_paths[index] = path
        ready_events[index].set()

    synth_tasks = [asyncio.create_task(synth(i, s)) for i, s in enumerate(sentences)]

    for i in range(len(sentences)):
        await ready_events[i].wait()
        await send_ipc_command(sock, {
            "command": ["loadfile", audio_paths[i], "append-play"]
        })
        print(f"Appended chunk {i}")

    await asyncio.gather(*synth_tasks)
    await listen_until_done(sock, len(sentences))

    sock.close()

    mpv_process.terminate()
    try:
        mpv_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        mpv_process.kill()
        mpv_process.wait()

# === Run ===
asyncio.run(synthesize_and_play(sentences, voice_id))