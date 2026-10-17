"""Orbit Payback API. uv run uvicorn api.main:app --reload --port 8000"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from api.agent import ask, has_xai_key, imagine, speak, transcribe
from api.chalk import enabled as chalk_enabled
from api.data import (
    DEFAULT_DIMS_M,
    get_close_approaches,
    place_satellites,
    rank_shells,
    shell_rows,
    warmup,
)

STATIC = Path(__file__).resolve().parent / "static"

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    warmup()
    yield


app = FastAPI(title="Orbit Payback", version="0.1.0", lifespan=lifespan)
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


class AskBody(BaseModel):
    question: str


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
    return {
        "ok": True,
        "xai": has_xai_key(),
        "chalk": chalk_enabled(),
        "reasoner": "chalk" if chalk_enabled() else "local",
    }


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
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set. Put it in .env to enable the agent.")
    try:
        return ask(body.question)
    except Exception as exc:
        raise HTTPException(502, f"Grok request failed: {exc}") from exc


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
        raise HTTPException(502, f"STT failed: {exc}") from exc
    return {"text": text}


@app.post("/imagine")
def post_imagine(body: ImagineBody):
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set.")
    try:
        return imagine(body.prompt)
    except Exception as exc:
        raise HTTPException(502, f"Imagine failed: {exc}") from exc


@app.post("/speak")
def post_speak(body: SpeakBody):
    if not has_xai_key():
        raise HTTPException(503, "XAI_API_KEY is not set. Put it in .env to enable voice.")
    try:
        audio = speak(body.text)
    except Exception as exc:
        raise HTTPException(502, f"Voice request failed: {exc}") from exc
    return Response(content=audio, media_type="audio/mpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
