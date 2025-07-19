import os
import signal
import sys

pid_file = "/tmp/edge_tts_reader.pid"

def stop_reader():
    if not os.path.exists(pid_file):
        print("No active edge-tts reader found.")
        return

    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        print("Corrupted PID file.")
        os.remove(pid_file)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to process {pid}.")
    except ProcessLookupError:
        print("Process not found. Removing stale PID file.")
    except PermissionError:
        print("Permission denied. Try running with sudo?")
        return
    finally:
        if os.path.exists(pid_file):
            os.remove(pid_file)

if __name__ == "__main__":
    stop_reader()
