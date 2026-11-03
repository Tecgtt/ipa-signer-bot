# Dockerfile for iOS IPA Signer Telegram Bot

FROM python:3.11-slim

# Prevent buffering and pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies and compiler
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libssl-dev \
    libminizip-dev \
    pkg-config \
    zlib1g-dev \
    openssl \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Clone and compile zsign using official Linux build makefile
RUN git clone --depth 1 https://github.com/zhlynn/zsign.git /tmp/zsign \
    && cd /tmp/zsign/build/linux \
    && make \
    && (cp /tmp/zsign/bin/zsign /usr/local/bin/zsign || cp zsign /usr/local/bin/zsign || find /tmp/zsign -name "zsign" -type f -exec cp {} /usr/local/bin/zsign \;) \
    && chmod +x /usr/local/bin/zsign \
    && rm -rf /tmp/zsign

# Set working directory
WORKDIR /app

# Copy dependencies list and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && (pip install --no-cache-dir cryptg || true)

# Copy source code
COPY . /app/

# Create persistent storage directories
RUN mkdir -p /app/data /app/temp

# Expose Render standard ports
EXPOSE 8080 10000

# Run bot
CMD ["python", "main.py"]
