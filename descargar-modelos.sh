#!/usr/bin/env bash
# Descarga los modelos de voz (≈ 450 MB) en ./models. Se ejecuta una sola vez.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models/piper salida

KOKORO=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -f "models/$f" ] || curl -fL --progress-bar -o "models/$f" "$KOKORO/$f"
done

# Voces de Piper en español (España, México, Argentina). Quita las que no quieras.
PIPER=https://huggingface.co/rhasspy/piper-voices/resolve/main/es
for v in es_MX-claude-high es_MX-ald-medium es_AR-daniela-high es_ES-davefx-medium \
         es_ES-sharvard-medium es_ES-carlfm-x_low es_ES-mls_9972-low es_ES-mls_10246-low; do
  pais="${v%%-*}"; resto="${v#*-}"; nombre="${resto%-*}"; calidad="${resto##*-}"
  for ext in onnx onnx.json; do
    [ -f "models/piper/$v.$ext" ] || curl -fL --progress-bar -o "models/piper/$v.$ext" "$PIPER/$pais/$nombre/$calidad/$v.$ext"
  done
done
echo "✓ Modelos listos en ./models"
