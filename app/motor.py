"""
Motor de voz local: Kokoro (onnx) y Piper. Sin tokens, sin internet.

Reglas del proyecto:
- El texto manda: nada de recortar el audio para que cuadre con otra cosa.
- Una sola voz por canal (la voz es la marca), pero el estudio deja probarlas todas.
- Devuelve SIEMPRE el audio y sus metadatos (motor, voz, velocidad, duración).
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

# Kokoro trae una tabla de voces; estas son las que hablan español (es-es).
KOKORO_VOCES = {
    "ef_dora": {"nombre": "Dora", "genero": "femenina", "idioma": "es"},
    "em_alex": {"nombre": "Alex", "genero": "masculina", "idioma": "es"},
    "em_santa": {"nombre": "Santa", "genero": "masculina", "idioma": "es"},
}

_kokoro = None
# Una síntesis a la vez: con 2 CPUs no se gana nada en paralelo, y dos peticiones
# simultáneas podían cargar Kokoro DOS veces (311 MB cada una) con un tope de 2 GB.
_turno = threading.Lock()

FORMATOS = ("mp3", "wav")


def _kokoro_motor():
    """Carga perezosa: el modelo son 311 MB y no todas las peticiones lo usan."""
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    return _kokoro


# Género y nombre humano de cada voz: el archivo no lo dice y "mls_9972" no es
# algo que se pueda poner en un desplegable.
PIPER_FICHA = {
    "es_ES-davefx-medium":  ("Dave",    "masculina", "España"),
    "es_ES-carlfm-x_low":   ("Carlos",  "masculina", "España"),
    "es_ES-sharvard-medium": ("Sharvard", "femenina", "España"),
    "es_ES-mls_9972-low":   ("Marta",   "femenina", "España"),
    "es_ES-mls_10246-low":  ("Lucía",   "femenina", "España"),
    "es_MX-claude-high":    ("Claudio", "masculina", "México"),
    "es_MX-ald-medium":     ("Aldo",    "masculina", "México"),
    "es_AR-daniela-high":   ("Daniela", "femenina", "Argentina"),
}

IDIOMA_POR_PREFIJO = {"es_ES": "España", "es_MX": "México", "es_AR": "Argentina"}


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
    """Lo que el estudio muestra en el desplegable."""
    return {
        "kokoro": {"etiqueta": "Kokoro (más natural, más lento)", "voces": KOKORO_VOCES},
        "piper": {"etiqueta": "Piper (más rápido, algo más plano)", "voces": piper_voces()},
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
    """El estudio recibe texto del guion: fuera etiquetas de ElevenLabs y marcas."""
    texto = re.sub(r"<break[^>]*/?>", " ", texto)      # <break time="0.4s" />
    texto = re.sub(r"\[[a-z ]+\]", " ", texto)          # [slow], [warmly]
    texto = re.sub(r"[*_`#]+", " ", texto)              # markdown suelto
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r" *\n *", "\n", texto).strip()        # sin espacios al borde de cada línea


def _wav_a_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)],
        check=True,
    )


def _duracion(wav: Path) -> float:
    with wave.open(str(wav), "rb") as fh:
        return fh.getnframes() / float(fh.getframerate())


def _parrafos(texto: str) -> list[str]:
    """Kokoro rinde mejor por trozos; además así el progreso es visible."""
    trozos = [t.strip() for t in re.split(r"\n\s*\n", texto) if t.strip()]
    return trozos or [texto]


def _nombre_base() -> str:
    """Único aunque lleguen dos peticiones en el mismo segundo: con solo la hora,
    la segunda sobrescribía el audio de la primera y su URL servía el equivocado.
    Empieza por la hora para que el historial siga ordenando bien a ojo."""
    return f"voz_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def genera(texto: str, motor: str = "kokoro", voz: str | None = None, velocidad: float = 0.92,
           formato: str = "mp3", nombre: str | None = None) -> Resultado:
    texto = _limpia(texto)
    if not texto:
        raise ValueError("No hay texto que leer")
    if len(texto) > 40000:
        raise ValueError("Texto demasiado largo (máximo 40.000 caracteres)")
    if formato not in FORMATOS:
        raise ValueError(f"Formato desconocido: {formato} (usa mp3 o wav)")
    velocidad = max(0.5, min(1.5, float(velocidad)))

    # Validar la voz ANTES de tocar disco o modelos.
    if motor == "kokoro":
        voz = voz or "em_alex"
        if voz not in KOKORO_VOCES:
            raise ValueError(f"Voz desconocida para Kokoro: {voz}")
    elif motor == "piper":
        voz = voz or "es_ES-davefx-medium"
        # Solo voces del catálogo: el nombre va a una ruta y "../x" saldría de la carpeta.
        if voz not in piper_voces():
            raise ValueError(f"Voz desconocida para Piper: {voz}")
    else:
        raise ValueError(f"Motor desconocido: {motor}")

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
                    piezas.append(np.zeros(int(sr * 0.35), dtype=audio.dtype))  # pausa entre párrafos
            sf.write(str(wav), np.concatenate(piezas), sr)
        else:
            # Piper controla el ritmo con length_scale (mayor = más lento).
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
