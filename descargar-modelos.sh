#!/usr/bin/env bash
# Downloads the voice models (≈ 450 MB) into ./models. Run it once.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p models/piper salida

KOKORO=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -f "models/$f" ] || curl -fL --progress-bar -o "models/$f" "$KOKORO/$f"
done

# Spanish Piper voices (Spain, Mexico, Argentina). Remove the ones you don't want.
PIPER=https://huggingface.co/rhasspy/piper-voices/resolve/main/es
for v in es_MX-claude-high es_MX-ald-medium es_AR-daniela-high es_ES-davefx-medium \
         es_ES-sharvard-medium es_ES-carlfm-x_low es_ES-mls_9972-low es_ES-mls_10246-low; do
  pais="${v%%-*}"; resto="${v#*-}"; nombre="${resto%-*}"; calidad="${resto##*-}"
  for ext in onnx onnx.json; do
    [ -f "models/piper/$v.$ext" ] || curl -fL --progress-bar -o "models/piper/$v.$ext" "$PIPER/$pais/$nombre/$calidad/$v.$ext"
  done
done
echo "✓ Modelos listos en ./models"
