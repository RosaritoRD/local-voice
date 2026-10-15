"""
Local voice engine: Kokoro (onnx) and Piper. No tokens, no internet.

Project rules:
- The text rules: never trim the audio to make it fit something else.
- One voice per channel (the voice is the brand), but the studio lets you try them all.
- ALWAYS return the audio plus its metadata (engine, voice, speed, duration).
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import dataclass, asdict
from pathlib import Path

MODELS = Path(os.environ.get("VOZ_MODELS", "/models"))
OUT = Path(os.environ.get("VOZ_SALIDA", "/salida"))

# Kokoro ships a voice table; these are the Spanish-speaking ones (es-es).
KOKORO_VOCES = {
    "ef_dora": {"nombre": "Dora", "genero": "female", "idioma": "es"},
    "em_alex": {"nombre": "Alex", "genero": "male", "idioma": "es"},
    "em_santa": {"nombre": "Santa", "genero": "male", "idioma": "es"},
}

_kokoro = None
# One synthesis at a time: with 2 CPUs nothing is gained in parallel, and two
# simultaneous requests could load Kokoro TWICE (311 MB each) under a 2 GB cap.
_turno = threading.Lock()

FORMATOS = ("mp3", "wav")


def _kokoro_motor():
    """Lazy load: the model is 311 MB and not every request needs it."""
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    return _kokoro


# Gender and a human name for each voice: the file doesn't say, and "mls_9972"
# isn't something you can put in a dropdown.
PIPER_FICHA = {
    "es_ES-davefx-medium":  ("Dave",    "male", "Spain"),
    "es_ES-carlfm-x_low":   ("Carlos",  "male", "Spain"),
    "es_ES-sharvard-medium": ("Sharvard", "female", "Spain"),
    "es_ES-mls_9972-low":   ("Marta",   "female", "Spain"),
    "es_ES-mls_10246-low":  ("Lucía",   "female", "Spain"),
    "es_MX-claude-high":    ("Claudio", "male", "Mexico"),
    "es_MX-ald-medium":     ("Aldo",    "male", "Mexico"),
    "es_AR-daniela-high":   ("Daniela", "female", "Argentina"),
}

IDIOMA_POR_PREFIJO = {"es_ES": "Spain", "es_MX": "Mexico", "es_AR": "Argentina"}


def piper_voces() -> dict:
    voces = {}
    carpeta = MODELS / "piper"
    for onnx in sorted(carpeta.glob("*.onnx")):
        clave = onnx.stem
        nombre, genero, pais = PIPER_FICHA.get(
            clave, (clave.split("-")[1].capitalize(), "—", IDIOMA_POR_PREFIJO.get(clave[:5], "—")))
        calidad = clave.rsplit("-", 1)[-1]          # x_low | low | medium | high
        voces[clave] = {"nombre": nombre, "genero": genero, "idioma": pais, "calidad": calidad}
    return voces


def catalogo() -> dict:
    """What the studio shows in the dropdown."""
    return {
        "kokoro": {"etiqueta": "Kokoro (more natural, slower)", "voces": KOKORO_VOCES},
        "piper": {"etiqueta": "Piper (faster, flatter)", "voces": piper_voces()},
    }


@dataclass
class Resultado:
    ruta: str
    motor: str
    voz: str
    velocidad: float
    duracion_s: float
    caracteres: int
    segundos_de_proceso: float
    formato: str

    def dict(self) -> dict:
        return asdict(self)


def _limpia(texto: str) -> str:
    """The studio gets script text: strip ElevenLabs tags and markup."""
    texto = re.sub(r"<break[^>]*/?>", " ", texto)      # <break time="0.4s" />
    texto = re.sub(r"\[[a-z ]+\]", " ", texto)          # [slow], [warmly]
    texto = re.sub(r"[*_`#]+", " ", texto)              # stray markdown
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r" *\n *", "\n", texto).strip()        # no spaces at the edges of each line


def _wav_a_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)],
        check=True,
    )


def _duracion(wav: Path) -> float:
    with wave.open(str(wav), "rb") as fh:
        return fh.getnframes() / float(fh.getframerate())


def _parrafos(texto: str) -> list[str]:
    """Kokoro works better in chunks; it also makes progress visible."""
    trozos = [t.strip() for t in re.split(r"\n\s*\n", texto) if t.strip()]
    return trozos or [texto]


def _nombre_base() -> str:
    """Unique even if two requests arrive in the same second: with the time alone,
    the second overwrote the first one's audio and its URL served the wrong file.
    It starts with the time so the history still sorts nicely by eye."""
    return f"voz_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def genera(texto: str, motor: str = "kokoro", voz: str | None = None, velocidad: float = 0.92,
           formato: str = "mp3", nombre: str | None = None) -> Resultado:
    texto = _limpia(texto)
    if not texto:
        raise ValueError("There is no text to read")
    if len(texto) > 40000:
        raise ValueError("Text too long (40,000 characters max)")
    if formato not in FORMATOS:
        raise ValueError(f"Unknown format: {formato} (use mp3 or wav)")
    velocidad = max(0.5, min(1.5, float(velocidad)))

    # Validate the voice BEFORE touching disk or models.
    if motor == "kokoro":
        voz = voz or "em_alex"
        if voz not in KOKORO_VOCES:
            raise ValueError(f"Unknown Kokoro voice: {voz}")
    elif motor == "piper":
        voz = voz or "es_ES-davefx-medium"
        # Catalog voices only: the name goes into a path and "../x" would escape the folder.
        if voz not in piper_voces():
            raise ValueError(f"Unknown Piper voice: {voz}")
    else:
        raise ValueError(f"Unknown engine: {motor}")

    OUT.mkdir(parents=True, exist_ok=True)
    base = nombre or _nombre_base()
    wav = OUT / f"{base}.wav"
    t0 = time.time()

    with _turno:
        if motor == "kokoro":
            import numpy as np
            import soundfile as sf
            k = _kokoro_motor()
            parrafos = _parrafos(texto)
            piezas, sr = [], 24000
            for i, parrafo in enumerate(parrafos):
                audio, sr = k.create(parrafo, voice=voz, speed=velocidad, lang="es")
                piezas.append(audio)
                if i + 1 < len(parrafos):
                    piezas.append(np.zeros(int(sr * 0.35), dtype=audio.dtype))  # pause between paragraphs
            sf.write(str(wav), np.concatenate(piezas), sr)
        else:
            # Piper sets the pace with length_scale (higher = slower).
            subprocess.run(
                ["piper", "--model", str(MODELS / "piper" / f"{voz}.onnx"), "--output_file", str(wav),
                 "--length_scale", f"{1 / velocidad:.3f}", "--sentence_silence", "0.35"],
                input=texto.encode(), check=True, capture_output=True,
            )

    duracion = _duracion(wav)
    salida = wav
    if formato == "mp3":
        salida = OUT / f"{base}.mp3"
        _wav_a_mp3(wav, salida)
        wav.unlink(missing_ok=True)

    return Resultado(
        ruta=str(salida), motor=motor, voz=voz, velocidad=velocidad,
        duracion_s=round(duracion, 2), caracteres=len(texto),
        segundos_de_proceso=round(time.time() - t0, 1), formato=formato,
    )
