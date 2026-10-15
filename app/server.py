"""
Voice studio API. The container serves the page itself (index.html), with
oauth2-proxy in front, same as your other app.

  GET  /api/voces                 catalog (engines + voices)
  POST /api/generar               { texto, motor, voz, velocidad, formato } → metadata + url
  GET  /api/audio/<archivo>       download/listen
  GET  /api/historial             latest generations
  GET  /health
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

import motor

app = FastAPI(title="Voz local — voice studio", docs_url=None, redoc_url=None)
AQUI = Path(__file__).parent


class Peticion(BaseModel):
    texto: str = Field(min_length=1, max_length=40000)
    motor: str = "kokoro"
    voz: str | None = None
    velocidad: float = 0.92
    formato: str = "mp3"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/voces")
def voces():
    return {"ok": True, "catalogo": motor.catalogo()}


@app.post("/api/generar")
def generar(p: Peticion):
    try:
        r = motor.genera(p.texto, p.motor, p.voz, p.velocidad, p.formato)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # the engine can fail from lack of memory or a missing model
        raise HTTPException(status_code=500, detail=f"Could not generate the voice: {e}")
    archivo = Path(r.ruta).name
    return {"ok": True, **r.dict(), "url": f"/api/audio/{archivo}"}


@app.get("/api/audio/{archivo}")
def audio(archivo: str):
    ruta = (motor.OUT / archivo).resolve()
    if motor.OUT.resolve() not in ruta.parents or not ruta.exists():
        raise HTTPException(status_code=404, detail="Not found")
    tipo = "audio/mpeg" if ruta.suffix == ".mp3" else "audio/wav"
    return FileResponse(str(ruta), media_type=tipo, filename=archivo)


@app.get("/api/historial")
def historial(limite: int = 30):
    archivos = sorted(motor.OUT.glob("voz_*"), key=lambda p: p.stat().st_mtime, reverse=True)[:limite]
    return {"ok": True, "archivos": [
        {"archivo": f.name, "url": f"/api/audio/{f.name}", "kb": round(f.stat().st_size / 1024),
         "cuando": int(f.stat().st_mtime)} for f in archivos]}


@app.get("/", response_class=HTMLResponse)
def pantalla():
    index = AQUI / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Voice studio</h1><p>The page isn't installed yet.</p>", status_code=200)
    return HTMLResponse(index.read_text(encoding="utf-8"))
