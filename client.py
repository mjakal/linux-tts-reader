#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# client.py

import socket
import json
import argparse
import subprocess
import sys
import os
import time

SOCKET_PATH = "/tmp/enge_tts.sock"
DEFAULT_VOICE = "en-US-EmmaNeural"
SERVER_BINARY_NAME = "tts-server"  # Name of your compiled server file

def get_executable_path():
    """Finds the directory where the client executable is running."""
    # When frozen (compiled), sys.executable is the binary path.
    # When running as script, sys.argv[0] or os.getcwd() is used.
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(application_path, SERVER_BINARY_NAME)

def is_server_alive():
    """Checks if the socket allows connection."""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError):
        return False

def start_server_process():
    """Starts the server as a detached process."""
    server_path = get_executable_path()
    
    if not os.path.exists(server_path):
        # Fallback: Check if it's in the PATH
        server_path = SERVER_BINARY_NAME
    
    print(f"Server not running. Attempting to start: {server_path}...")
    
    try:
        # start_new_session=True is CRITICAL. 
        # It detaches the child process so it doesn't die when client exits.
        subprocess.Popen(
            [server_path],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print(f"Error: Could not find server binary at '{server_path}'.")
        print("Make sure 'tts-server' is in the same folder as this client.")
        sys.exit(1)

def send_request_with_retry(payload, retries=10):
    """Try to send request, starting server if needed."""
    
    # 1. Attempt connection
    if not is_server_alive():
        start_server_process()
        
        # 2. Loop until server is ready (Polling)
        server_ready = False
        print("Waiting for server to initialize...", end="", flush=True)
        for _ in range(retries):
            if is_server_alive():
                server_ready = True
                print(" Done.")
                break
            time.sleep(0.5) # Wait 0.5s between checks
            print(".", end="", flush=True)
        
        if not server_ready:
            print("\nError: Timed out waiting for server to start.")
            sys.exit(1)

    # 3. Send Data
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        client.send(json.dumps(payload).encode())
        response = client.recv(1024).decode()
        print(f"\n[Server]: {response}")
        client.close()
    except Exception as e:
        print(f"Communication Error: {e}")

def get_clipboard_text():
    try:
        return subprocess.check_output(
            ["xclip", "-out", "-selection", "primary"], 
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description="Client for TTS Server")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-t", "--text", type=str, help="Text to read")
    group.add_argument("-s", "--stop", action="store_true", help="Stop reading")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help="Voice ID")
    parser.add_argument("--no-clean", action="store_true", help="Disable server-side cleaning")
    
    args = parser.parse_args()

    # Construct payload
    payload = {}
    if args.stop:
        payload = {"command": "stop"}
    else:
        text = args.text if args.text else get_clipboard_text()
        if not text:
            print("No text found.")
            sys.exit(1)
        payload = {
            "command": "read", 
            "text": text, 
            "voice": args.voice, 
            "clean": not args.no_clean
        }

    send_request_with_retry(payload)

if __name__ == "__main__":
    main()