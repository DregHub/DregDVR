# Stage 1 — always pull latest Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.58.0 AS base

# Stage 2 — extend it
FROM base

# Install system dependencies for yt-dlp (ffmpeg) + tools you need
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        unzip \
        ffmpeg \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire application code
COPY . /_Dregg_DVR
WORKDIR /_Dregg_DVR

# Set Python to unbuffered mode
ENV PYTHONUNBUFFERED=1
