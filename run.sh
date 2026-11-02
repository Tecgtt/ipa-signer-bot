#!/usr/bin/env bash
# Quick start script for iOS IPA Signer Telegram Bot

cd "$(dirname "$0")"

echo "=== Starting iOS IPA Signer Bot ==="

# Check for .env file
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "[!] .env not found. Creating from .env.example..."
        cp .env.example .env
        echo "[!] Please edit .env with your BOT_TOKEN and run ./run.sh again."
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv || python3 -m virtualenv venv
fi

# Activate venv
source venv/bin/activate

# Install requirements
echo "[*] Installing/Verifying Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Start Bot
echo "[*] Launching Bot..."
python main.py
