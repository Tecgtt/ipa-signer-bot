#!/usr/bin/env bash
# Installation script for zsign (iOS IPA signing binary)

set -e

echo "=== Installing zsign IPA Signer ==="

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[*] Detected macOS."
    if command -v brew &>/dev/null; then
        echo "[*] Installing dependencies with Homebrew..."
        brew install openssl zlib minizip pkg-config
        rm -rf /tmp/zsign
        git clone --depth 1 https://github.com/zhlynn/zsign.git /tmp/zsign
        cd /tmp/zsign/build/macos
        make
        sudo cp /tmp/zsign/bin/zsign /usr/local/bin/zsign || cp /tmp/zsign/bin/zsign /usr/local/bin/zsign
        echo "[✅] zsign successfully installed to /usr/local/bin/zsign!"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[*] Detected Linux."
    sudo apt-get update
    sudo apt-get install -y build-essential git libssl-dev libminizip-dev pkg-config zlib1g-dev
    rm -rf /tmp/zsign
    git clone --depth 1 https://github.com/zhlynn/zsign.git /tmp/zsign
    cd /tmp/zsign/build/linux
    make
    sudo cp /tmp/zsign/bin/zsign /usr/local/bin/zsign || cp /tmp/zsign/bin/zsign /usr/local/bin/zsign
    echo "[✅] zsign successfully installed to /usr/local/bin/zsign!"
fi

echo "Verifying zsign installation:"
zsign -v || echo "zsign ready"
