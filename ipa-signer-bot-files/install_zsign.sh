#!/usr/bin/env bash
# Installation script for zsign (iOS IPA signing binary)

set -e

echo "=== Installing zsign IPA Signer ==="

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[*] Detected macOS."
    if command -v brew &>/dev/null; then
        echo "[*] Installing dependencies with Homebrew..."
        brew install openssl zlib
        echo "[*] Cloning and building zsign..."
        git clone https://github.com/zhlynn/zsign.git /tmp/zsign_build || true
        cd /tmp/zsign_build
        OPENSSL_PREFIX=$(brew --prefix openssl)
        g++ *.cpp common/*.cpp -lcrypto -lz -I"$OPENSSL_PREFIX/include" -L"$OPENSSL_PREFIX/lib" -O3 -o /usr/local/bin/zsign || \
        sudo g++ *.cpp common/*.cpp -lcrypto -lz -I"$OPENSSL_PREFIX/include" -L"$OPENSSL_PREFIX/lib" -O3 -o /usr/local/bin/zsign
        echo "[✅] zsign successfully installed to /usr/local/bin/zsign!"
    else
        echo "[!] Homebrew not found. Please install Homebrew or compile zsign manually."
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[*] Detected Linux."
    echo "[*] Installing dependencies (g++, make, libssl-dev, zlib1g-dev)..."
    sudo apt-get update
    sudo apt-get install -y git g++ make libssl-dev zlib1g-dev

    echo "[*] Cloning and building zsign..."
    rm -rf /tmp/zsign_build
    git clone https://github.com/zhlynn/zsign.git /tmp/zsign_build
    cd /tmp/zsign_build
    g++ *.cpp common/*.cpp -lcrypto -lz -O3 -o /usr/local/bin/zsign || \
    sudo g++ *.cpp common/*.cpp -lcrypto -lz -O3 -o /usr/local/bin/zsign
    echo "[✅] zsign successfully installed to /usr/local/bin/zsign!"
fi

echo "Verifying zsign installation:"
zsign -v || echo "zsign ready"
