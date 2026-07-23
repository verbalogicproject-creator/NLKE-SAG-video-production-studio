FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV SAG_VIDEO_DATABASE_PATH=/data/sag-video.db \
    SAG_VIDEO_ARTIFACT_DIR=/artifacts \
    PORT=8080

EXPOSE 8080
CMD ["sh", "-c", "uvicorn sag_video.app:app --host 0.0.0.0 --port ${PORT}"]
