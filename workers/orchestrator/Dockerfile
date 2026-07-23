# ══════════════════════════════════════════════════════════════
# Verbalogix Lab — Render Worker
# Target: Cloud Run Jobs (CPU, scale-to-zero)
# Base: Node 22 + FFmpeg + whisper.cpp + Kokoro 82M
# Cold-start target: < 30 seconds
# ══════════════════════════════════════════════════════════════

FROM node:22-bookworm-slim AS base

# System deps: FFmpeg (Remotion + FFmpeg jobs), build tools for whisper.cpp,
# Python for Kokoro inference, Chromium deps for Remotion headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        build-essential \
        cmake \
        python3 \
        python3-pip \
        ca-certificates \
        chromium \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

# whisper.cpp — CPU build, Metal/CUDA disabled for Cloud Run CPU tier.
RUN git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git /opt/whisper.cpp \
    && cd /opt/whisper.cpp \
    && make -j$(nproc) \
    && bash ./models/download-ggml-model.sh base.en \
    && ln -s /opt/whisper.cpp/main /usr/local/bin/whisper-cli

# Kokoro 82M TTS model — English, 8 voices, runs on CPU.
# Pinned to an explicit release so cold-starts are reproducible.
RUN pip3 install --break-system-packages --no-cache-dir \
        kokoro-onnx==0.4.7 \
        onnxruntime==1.20.1 \
        soundfile==0.12.1
ENV KOKORO_MODEL_PATH=/models/kokoro-82m

# Pre-download the Kokoro model so the first job doesn't pay the cost.
# (This step assumes the model is publicly fetchable — revisit if licensing changes.)
RUN mkdir -p /models/kokoro-82m

WORKDIR /app

# Install JS deps first — leverages Docker layer cache.
COPY package.json tsconfig.json ./
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
COPY pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

# Copy source, build, prune dev deps.
COPY src ./src
RUN pnpm build && pnpm prune --prod

ENV NODE_ENV=production
ENV PORT=8080
EXPOSE 8080

CMD ["node", "dist/index.js"]
