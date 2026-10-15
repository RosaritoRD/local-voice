FROM python:3.11-slim

# espeak-ng: fonemizador que Kokoro y Piper usan para español.
# ffmpeg: convertir a mp3 y medir duración.
RUN apt-get update && apt-get install -y --no-install-recommends \
      espeak-ng libespeak-ng1 ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app
RUN useradd -m -u 1000 voz && mkdir -p /models /salida && chown -R voz /app /models /salida
USER voz
EXPOSE 8090
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
