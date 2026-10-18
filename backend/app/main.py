"""FastAPI entrypoint: REST for matches/plugins/recaps, WebSocket for the live feed."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import Orchestrator, Persona, get_llm
from .agents.ask_agent import AskAgent, LiveContext
from .speech import VOICES, get_speech
from .models import Match
from .pipeline import LivePipeline
from .plugins import describe_plugins
from .replay import ReplayEngine
from .store import MatchStore

DEFAULT_SEED = int(os.getenv("MATCH_SEED", "2"))  # seed 2: an eventful 2-2 with headed chances, good for demos
DEFAULT_MINUTES = int(os.getenv("MATCH_MINUTES", "20"))

store: MatchStore | None = None
llm = get_llm()
speech = get_speech()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = MatchStore()
    if llm.available:
        # Open the connection to the model now, so the first live commentary isn't slowed by a cold start.
        warmup = asyncio.create_task(llm.complete("Reply with: ok", "ok", max_tokens=3))
        warmup.add_done_callback(lambda t: t.exception())  # best effort; never crash startup
    if not store.list():
        await asyncio.to_thread(store.generate, DEFAULT_SEED, DEFAULT_MINUTES)
    yield


app = FastAPI(title="Inside the Game - Match Intelligence", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def _store() -> MatchStore:
    assert store is not None
    return store


def _match(match_id: str) -> Match:
    match = _store().get(match_id)
    if match is None:
        raise HTTPException(404, f"Unknown match {match_id}")
    return match


class GenerateRequest(BaseModel):
    seed: int = Field(default=7, ge=0)
    minutes: int = Field(default=20, ge=2, le=90)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "llm": type(llm).__name__, "model": getattr(llm, "deployment", None),
            "voice": "Azure AI Speech" if speech else None}


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    lang: str = "en"
    kind: str | None = None


@app.post("/api/tts")
async def tts(req: TTSRequest) -> Response:
    """Spoken commentary: Azure AI Speech neural voice for the requested language, as MP3."""
    if speech is None:
        raise HTTPException(503, "Speech not configured")
    if req.lang not in VOICES:
        raise HTTPException(400, f"No voice for language {req.lang}")
    audio = await speech.synthesize(req.text, req.lang, req.kind)
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/matches")
def list_matches() -> list[dict]:
    return _store().list()


@app.post("/api/matches")
async def generate(req: GenerateRequest) -> dict:
    match = await asyncio.to_thread(_store().generate, req.seed, req.minutes)
    return {"match_id": match.meta.match_id, "final_score": match.meta.final_score}


@app.get("/api/matches/{match_id}")
def match_meta(match_id: str) -> dict:
    return _match(match_id).meta.model_dump()


@app.get("/api/matches/{match_id}/events")
def match_events(match_id: str, type: str | None = None) -> list[dict]:
    return [e.model_dump() for e in _match(match_id).events if type is None or e.type == type]


@app.get("/api/plugins")
def plugins() -> list[dict]:
    return describe_plugins()


@app.get("/api/agents")
def agents() -> list[dict]:
    return Orchestrator.describe_agents()


_recap_cache: dict[tuple, dict] = {}
_full_pass_cache: dict[str, tuple[list, dict]] = {}


def _full_pass(match: Match) -> tuple[list, dict]:
    """Run every plugin over the whole match once (for recaps and overlay export)."""
    match_id = match.meta.match_id
    if match_id not in _full_pass_cache:
        pipeline = LivePipeline(match)
        insights = []
        for frame in match.frames:
            insights.extend(pipeline.process(frame).insights)
        _full_pass_cache[match_id] = (insights, pipeline.snapshots())
    return _full_pass_cache[match_id]


@app.get("/api/matches/{match_id}/overlays")
async def overlays(match_id: str) -> dict:
    """Full broadcast cue timeline, for a graphics engine to sync against the feed clock."""
    match = _match(match_id)
    _, snapshots = await asyncio.to_thread(_full_pass, match)
    timeline = (snapshots.get("overlays") or {}).get("timeline", [])
    return {"match_id": match_id, "clock": "seconds since kickoff", "cues": timeline}


@app.get("/api/matches/{match_id}/recap")
async def recap(
    match_id: str,
    mode: str = "casual",
    lang: str = "en",
    favorite_team: str | None = None,
    favorite_player: str | None = None,
) -> dict:
    match = _match(match_id)
    persona = Persona(mode=mode, language=lang, favorite_team=favorite_team, favorite_player=favorite_player)
    key = (match_id, persona.model_dump_json())
    if key not in _recap_cache:
        insights, snapshots = await asyncio.to_thread(_full_pass, match)
        _recap_cache[key] = await Orchestrator(match.meta, llm).recap(insights, snapshots, match.meta.final_score, persona)
    return _recap_cache[key]


@app.websocket("/ws/live/{match_id}")
async def live(
    ws: WebSocket,
    match_id: str,
    speed: float = 1.0,
    mode: str = "casual",
    lang: str = "en",
    favorite_team: str | None = None,
    favorite_player: str | None = None,
    plugins: str | None = Query(default=None, description="comma-separated plugin names"),
):
    await ws.accept()
    match = _store().get(match_id)
    if match is None:
        await ws.send_json({"type": "error", "message": f"Unknown match {match_id}"})
        await ws.close()
        return

    pipeline = LivePipeline(match, plugins.split(",") if plugins else None)
    engine = ReplayEngine(match, speed)
    orchestrator = Orchestrator(match.meta, llm)
    ask_agent = AskAgent(llm)
    persona = Persona(mode=mode, language=lang, favorite_team=favorite_team, favorite_player=favorite_player)
    send_lock = asyncio.Lock()
    narration_tasks: set[asyncio.Task] = set()

    async def send(msg: dict) -> None:
        async with send_lock:
            await ws.send_json(msg)

    await send(
        {
            "type": "meta",
            "meta": match.meta.model_dump(),
            "plugins": describe_plugins(),
            "enabled": pipeline.enabled,
            "agents": orchestrator.describe(),
            "persona": persona.model_dump(),
            "speed": engine.speed,
        }
    )

    async def narrate(t: float, score: dict, insights: list, snapshots: dict, p: Persona) -> None:
        out = await orchestrator.narrate(t, score, insights, snapshots, p)
        if out is not None:
            await send({"type": "narration", **out})

    async def receiver() -> None:
        nonlocal persona
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "control":
                action = msg.get("action")
                if action == "pause":
                    engine.paused = True
                elif action == "play":
                    engine.paused = False
                elif action == "seek":
                    engine.seek(float(msg.get("t", 0)))
                if "speed" in msg:
                    engine.set_speed(float(msg["speed"]))
                await send({"type": "control_ack", "paused": engine.paused, "speed": engine.speed})
            elif kind == "plugins":
                pipeline.set_enabled(list(msg.get("enabled", [])))
                await send({"type": "plugins_ack", "enabled": pipeline.enabled})
            elif kind == "persona":
                persona = Persona(**{**persona.model_dump(), **msg.get("persona", {})})
                await send({"type": "persona_ack", "persona": persona.model_dump()})
            elif kind == "ask":
                question = str(msg.get("question", "")).strip()[:300]
                if question:
                    task = asyncio.create_task(answer(question, persona))
                    narration_tasks.add(task)
                    task.add_done_callback(narration_tasks.discard)

    async def answer(question: str, p: Persona) -> None:
        state = pipeline.state
        frame = state.frame
        ctx = LiveContext(
            meta=match.meta,
            t=frame.t if frame else 0.0,
            score=dict(frame.score) if frame else {"home": 0, "away": 0},
            snapshots=pipeline.snapshots(),
            events=list(state.events),
            favorite_player=p.favorite_player,
        )
        await send({"type": "answer", **(await ask_agent.answer(question, ctx, p))})

    async def sender() -> None:
        while True:
            async for frame, seeked in engine.ticks():
                if seeked:
                    await asyncio.to_thread(pipeline.seek, frame.f)
                result = pipeline.process(frame)
                await send(
                    {
                        "type": "tick",
                        "frame": frame.model_dump(),
                        "events": [e.model_dump() for e in result.events],
                        "plugins": result.payloads,
                        "insights": [i.model_dump() for i in result.insights],
                    }
                )
                if orchestrator.should_run(result.insights, frame.t):
                    task = asyncio.create_task(
                        narrate(frame.t, dict(frame.score), result.insights, pipeline.snapshots(), persona)
                    )
                    narration_tasks.add(task)
                    task.add_done_callback(narration_tasks.discard)
            await send({"type": "end", "final_score": match.meta.final_score})
            while engine.cursor >= len(engine.frames) and engine.pending_seek is None:
                await asyncio.sleep(0.1)  # stay connected; a seek restarts playback

    tasks = [asyncio.create_task(receiver()), asyncio.create_task(sender())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        for t in [*tasks, *narration_tasks]:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(BaseException):
                await t


# Production: serve the built frontend from the same origin (single container).
_static = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
