"""LVL 500 API. uv run uvicorn api.main:app --reload --port 8000"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from api.agent import ask, ask_without_grok, has_xai_key, imagine, speak, transcribe
from api.chalk import ping as chalk_ping, redact
from api.data import (
    DEFAULT_DIMS_M,
    get_close_approaches,
    place_satellites,
    rank_locations,
    rank_shells,
    shell_rows,
    warmup,
)

API_DIR = Path(__file__).resolve().parent
STATIC = API_DIR / "static"
ROOT = API_DIR.parent

load_dotenv(ROOT / ".env", override=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    warmup()
    yield


app = FastAPI(title="LVL 500", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlaceBody(BaseModel):
    alt_km: float
    inc_deg: float = 53
    dims_m: list[float] = Field(default_factory=lambda: list(DEFAULT_DIMS_M))
    count: int = Field(default=1, ge=1, le=1_000_000)


class AskContext(BaseModel):
    altitude_km: float | None = None
    inclination_deg: float | None = None
    selected_norad: int | None = None


class AskBody(BaseModel):
    question: str
    context: AskContext | None = None


class SpeakBody(BaseModel):
    text: str


class ImagineBody(BaseModel):
    prompt: str


def _parse_dims(dims: str) -> list[float]:
    parts = [p.strip() for p in dims.split(",") if p.strip()]
    if not parts:
        return list(DEFAULT_DIMS_M)
    return [float(p) for p in parts]


@app.get("/")
def demo():
    return FileResponse(STATIC / "demo.html")


@app.get("/health")
def health():
    chalk = chalk_ping()
    up = bool(chalk.get("ok"))
    body = {
        "ok": True,
        "xai": has_xai_key(),
        "chalk": up,
        "reasoner": "chalk" if up else "local",
    }
    detail = chalk.get("detail")
    if not up and detail and detail != "unset":
        body["chalk_error"] = detail
    return body


@app.get("/shells")
def get_shells():
    return {
        "source": "CelesTrak SATCAT, tracked objects only (lower bound)",
        "shells": shell_rows(),
    }


@app.post("/place")
def post_place(body: PlaceBody):
    try:
        return place_satellites(body.alt_km, body.inc_deg, body.dims_m, body.count)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/locations")
def get_locations(
    region: str,
    alt_km: float | None = None,
    top: int = Query(default=5, ge=1, le=12),
):
    try:
        return rank_locations(region, alt_km, top)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/rank")
def get_rank(
    dims: str = "4,2,1",
    count: int = Query(default=1000, ge=1, le=1_000_000),
    top: int = Query(default=10, ge=1, le=30),
):
    return {"count": count, "dims_m": _parse_dims(dims), "rows": rank_shells(_parse_dims(dims), count, top)}


@app.get("/close_approaches")
def close_approaches(
    alt_km: float | None = None,
    limit: int = Query(default=10, ge=1, le=50),
):
    return get_close_approaches(alt_km, limit)


@app.post("/ask")
def post_ask(body: AskBody):
    context = body.context.model_dump() if body.context else None
    try:
        if has_xai_key():
            return ask(body.question, context=context)
        return ask_without_grok(body.question, context)
    except Exception as exc:
        label = "Grok" if has_xai_key() else "Ask"
        raise HTTPException(502, f"{label} request failed: {redact(str(exc))}") from exc


@app.post("/listen")
async def post_listen(file: UploadFile = File(...)):
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set. Put it in .env to enable voice.")
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "empty audio")
    try:
        text = transcribe(audio, file.filename or "clip.webm", file.content_type or "audio/webm")
    except Exception as exc:
        raise HTTPException(502, f"STT failed: {redact(str(exc))}") from exc
    return {"text": text}


@app.post("/imagine")
def post_imagine(body: ImagineBody):
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set.")
    try:
        return imagine(body.prompt)
    except Exception as exc:
        raise HTTPException(502, f"Imagine failed: {redact(str(exc))}") from exc


@app.post("/speak")
def post_speak(body: SpeakBody):
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set. Put it in .env to enable voice.")
    try:
        audio = speak(body.text)
    except Exception as exc:
        raise HTTPException(502, f"Voice request failed: {redact(str(exc))}") from exc
    return Response(content=audio, media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
