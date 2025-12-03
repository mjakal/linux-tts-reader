#!/bin/bash

# Install requirements
# sudo apt install jq netcat-openbsd xclip

# --- Configuration ---
SOCKET_PATH="/tmp/enge_tts.sock"
SERVER_BIN="./tts-server"  # Assumes server is in the same dir
DEFAULT_VOICE="en-US-EmmaNeural"

# --- Helper Functions ---

# Function to start server if not running
ensure_server_running() {
    if [ ! -S "$SOCKET_PATH" ]; then
        # Check if server binary exists in current dir, or fallback to PATH
        if [ -f "$SERVER_BIN" ]; then
            REAL_SERVER_PATH="$SERVER_BIN"
        else
            REAL_SERVER_PATH="tts-server" # Hope it's in PATH
        fi

        # Start server in background, detach output
        # nohup allows it to survive after this script exits
        nohup "$REAL_SERVER_PATH" >/dev/null 2>&1 &
        
        # Wait for socket to appear (max 2 seconds)
        local retries=20
        while [ $retries -gt 0 ]; do
            if [ -S "$SOCKET_PATH" ]; then
                return 0
            fi
            sleep 0.1
            ((retries--))
        done
        
        echo "Error: Timed out waiting for server to start."
        exit 1
    fi
}

# --- Argument Parsing ---
TEXT=""
STOP=false
VOICE="$DEFAULT_VOICE"
CLEAN=true

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -t|--text) TEXT="$2"; shift ;;
        -s|--stop) STOP=true ;;
        -v|--voice) VOICE="$2"; shift ;;
        --no-clean) CLEAN=false ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# --- Logic ---

# 1. Construct JSON Payload
if [ "$STOP" = true ]; then
    JSON_PAYLOAD=$(jq -n --arg cmd "stop" '{command: $cmd}')
else
    # If no text provided, get from clipboard
    if [ -z "$TEXT" ]; then
        TEXT=$(xclip -out -selection primary 2>/dev/null)
        if [ -z "$TEXT" ]; then
            echo "Error: No text found in clipboard."
            exit 1
        fi
    fi
    
    # Construct JSON safely using jq
    JSON_PAYLOAD=$(jq -n \
                  --arg cmd "read" \
                  --arg txt "$TEXT" \
                  --arg vc "$VOICE" \
                  --argjson cl "$CLEAN" \
                  '{command: $cmd, text: $txt, voice: $vc, clean: $cl}')
fi

# 2. Ensure Server is Alive
ensure_server_running

# 3. Send Data via Netcat (nc)
# -U specifies Unix Domain Socket
# -w 1 sets a timeout of 1 second for response
echo "$JSON_PAYLOAD" | nc -U -w 1 "$SOCKET_PATH"
