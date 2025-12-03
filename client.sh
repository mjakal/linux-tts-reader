#!/bin/bash

# Install requirements
# sudo apt install jq netcat-openbsd xclip

# --- Configuration ---
SOCKET_PATH="/tmp/enge_tts.sock"
# Attempt to find the directory of this script to locate the server binary next to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_BIN="$SCRIPT_DIR/tts-server" 
DEFAULT_VOICE="en-US-EmmaNeural"

# --- Helper Functions ---

# Function to start server if not running
ensure_server_running() {
    # Check if socket exists
    if [ ! -S "$SOCKET_PATH" ]; then
        # Check if server binary exists in current dir, or fallback to PATH
        if [ -f "$SERVER_BIN" ]; then
            REAL_SERVER_PATH="$SERVER_BIN"
        elif command -v tts-server &> /dev/null; then
            REAL_SERVER_PATH="tts-server"
        else
            echo "Error: Server binary 'tts-server' not found in $SCRIPT_DIR or system PATH." >&2
            echo "Please compile server.py and place it next to this script." >&2
            exit 1
        fi

        echo "Socket not found. Starting server..." >&2
        
        # Start server in background, detach output so it survives script exit
        nohup "$REAL_SERVER_PATH" >/dev/null 2>&1 &
        
        # Wait for socket to appear (max 5 seconds)
        local retries=50
        while [ $retries -gt 0 ]; do
            if [ -S "$SOCKET_PATH" ]; then
                return 0
            fi
            sleep 0.1
            ((retries--))
        done
        
        echo "Error: Timed out waiting for server to start." >&2
        exit 1
    fi
}

# --- Argument Parsing ---
TEXT=""
STOP=false
LIST=false
VOICE="$DEFAULT_VOICE"
CLEAN=true

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -t|--text) TEXT="$2"; shift ;;
        -s|--stop) STOP=true ;;
        -l|--list-voices) LIST=true ;;
        -v|--voice) VOICE="$2"; shift ;;
        --no-clean) CLEAN=false ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# --- Logic ---

# 1. Construct JSON Payload & Set Timeouts
if [ "$STOP" = true ]; then
    JSON_PAYLOAD=$(jq -n --arg cmd "stop" '{command: $cmd}')
    TIMEOUT=2
elif [ "$LIST" = true ]; then
    JSON_PAYLOAD=$(jq -n --arg cmd "list_voices" '{command: $cmd}')
    # Listing voices involves an API call to MS Edge, so we need a longer timeout
    TIMEOUT=10 
else
    # If no text provided, get from clipboard
    if [ -z "$TEXT" ]; then
        # Use primary selection (highlight) by default. Change to 'clipboard' for Ctrl+C.
        TEXT=$(xclip -out -selection primary 2>/dev/null)
        if [ -z "$TEXT" ]; then
            echo "Error: No text found in clipboard." >&2
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
    TIMEOUT=2
fi

# 2. Ensure Server is Alive
ensure_server_running

# 3. Send Data via Netcat (nc)
# -U specifies Unix Domain Socket
# -w sets timeout (critical for waiting for the list_voices response)
echo "$JSON_PAYLOAD" | nc -U -w "$TIMEOUT" "$SOCKET_PATH"