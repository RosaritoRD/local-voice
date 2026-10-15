"""
API del estudio de voz. La pantalla la sirve el propio contenedor (index.html)
y detrás va oauth2-proxy, igual que tu otra app.

  GET  /api/voces                 catálogo (motores + voces)
  POST /api/generar               { texto, motor, voz, velocidad, formato } → metadatos + url
  GET  /api/audio/<archivo>       descarga/escucha
  GET  /api/historial             últimas generaciones
  GET  /health
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

import motor

app = FastAPI(title="Voz local — estudio", docs_url=None, redoc_url=None)
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
    except Exception as e:  # el motor puede fallar por memoria o modelo ausente
        raise HTTPException(status_code=500, detail=f"No se pudo generar la voz: {e}")
    archivo = Path(r.ruta).name
    return {"ok": True, **r.dict(), "url": f"/api/audio/{archivo}"}


@app.get("/api/audio/{archivo}")
def audio(archivo: str):
    ruta = (motor.OUT / archivo).resolve()
    if motor.OUT.resolve() not in ruta.parents or not ruta.exists():
        raise HTTPException(status_code=404, detail="No existe")
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
        return HTMLResponse("<h1>Estudio de voz</h1><p>La pantalla aún no está instalada.</p>", status_code=200)
    return HTMLResponse(index.read_text(encoding="utf-8"))
