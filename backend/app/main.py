"""FastAPI entrypoint: REST for matches/plugins/recaps, WebSocket for the live feed."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ratelimit, telemetry
from .agents import Orchestrator, Persona, get_llm
from .agents.ask_agent import AskAgent, LiveContext
from .a2a_server import build_routes as build_a2a_routes, minute_of
from .agents.explain_agent import clean, explain, highlights
from .commentary import CommentaryScheduler
from .speech import VOICES, get_speech
from .models import Match
from .moments import find_moments, frames_between, pick_highlights
from .pipeline import LivePipeline
from .plugins import describe_plugins
from .replay import ReplayEngine
from .store import MatchStore

DEFAULT_SEED = int(os.getenv("MATCH_SEED", "2"))  # seed 2: an eventful 2-2 with headed chances, good for demos
DEFAULT_MINUTES = int(os.getenv("MATCH_MINUTES", "20"))

store: MatchStore | None = None
telemetry.setup()  # before the model and speech clients are created, so their calls are traced
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
    prewarm = None
    if llm.available and os.getenv("PREWARM", "1") == "1":
        first = store.get(store.list()[0]["match_id"])
        if first is not None:
            prewarm = asyncio.create_task(_prewarm(first))
    yield
    if prewarm is not None:
        prewarm.cancel()


app = FastAPI(title="Inside the Game - Match Intelligence", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)  # replay frames for highlights are ~0.5 MB of JSON
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
            "voice": "Azure AI Speech" if speech else None,
            "tracing": "Azure Application Insights" if telemetry.enabled else None}


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    lang: str = "en"
    kind: str | None = None


@app.post("/api/tts")
async def tts(req: TTSRequest, request: Request) -> Response:
    """Spoken commentary: Azure AI Speech neural voice for the requested language, as MP3."""
    ratelimit.check(request, "tts")
    if speech is None:
        raise HTTPException(503, "Speech not configured")
    if req.lang not in VOICES:
        raise HTTPException(400, f"No voice for language {req.lang}")
    with telemetry.span("tts", **{"tts.language": req.lang, "tts.kind": req.kind, "tts.chars": len(req.text)}):
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
    request: Request,
    match_id: str,
    mode: str = "casual",
    lang: str = "en",
    favorite_team: str | None = None,
    favorite_player: str | None = None,
) -> dict:
    ratelimit.check(request, "ai")
    match = _match(match_id)
    persona = Persona(mode=mode, language=lang, favorite_team=favorite_team, favorite_player=favorite_player)
    key = (match_id, persona.model_dump_json())
    if key not in _recap_cache:
        insights, snapshots = await asyncio.to_thread(_full_pass, match)
        _recap_cache[key] = await Orchestrator(match.meta, llm).recap(insights, snapshots, match.meta.final_score, persona)
    return _recap_cache[key]


_moments_cache: dict[str, list[dict]] = {}
_narration_cache: dict[tuple, dict] = {}
_clip_cache: dict[tuple, dict] = {}
NARRATION_CACHE_SIZE = 5000
_explain_cache: dict[tuple, dict] = {}


def _moments(match: Match) -> list[dict]:
    if match.meta.match_id not in _moments_cache:
        _moments_cache[match.meta.match_id] = find_moments(match)
    return _moments_cache[match.meta.match_id]


@app.get("/api/matches/{match_id}/moments")
def moments(match_id: str, upto: float | None = None) -> list[dict]:
    """Every shot with its build-up and shot context; `upto` hides what hasn't happened yet."""
    return [m for m in _moments(_match(match_id)) if upto is None or m["t"] <= upto]


async def _explained(match: Match, moment: dict, persona: Persona, depth: str = "full") -> dict:
    key = ("explain", match.meta.match_id, moment["id"], persona.model_dump_json(), depth)
    if key not in _explain_cache:
        with telemetry.span("explain", **{"moment.id": moment["id"], "moment.kind": moment["kind"], "depth": depth}):
            out = await explain(llm, match.meta, moment, persona, depth)
        out["frames"] = frames_between(match, moment["start"], moment["end"])
        if not clean(out["trace"]):
            return out
        _explain_cache[key] = out
    return _explain_cache[key]


async def _reel(match: Match, upto: float | None, persona: Persona) -> dict:
    end_t = match.frames[-1].t
    finished = upto is None or upto >= end_t
    upto_t = end_t if finished else float(upto)
    clips = pick_highlights(_moments(match), upto_t)
    key = ("reel", match.meta.match_id, tuple(c["id"] for c in clips), finished, persona.model_dump_json())
    if key not in _explain_cache:
        frame = match.frames[min(len(match.frames) - 1, int(upto_t * match.meta.fps))]
        with telemetry.span("highlights", **{"clips": len(clips), "finished": finished}):
            out = await highlights(llm, match.meta, clips, dict(frame.score), int(upto_t // 60), finished, persona, _clip_cache)
        out = {**out, "items": [{**item, "frames": frames_between(match, item["moment"]["clip_start"], item["moment"]["end"])}
                                for item in out["items"]]}
        if not clean(out["trace"]):
            return out
        _explain_cache[key] = out
    return _explain_cache[key]


async def _prewarm(match: Match) -> None:
    """Fill the replay caches for the default viewers after a (re)start, so the first clicks are instant."""
    sem = asyncio.Semaphore(3)

    async def one(coro) -> None:
        async with sem:
            try:
                await coro
            except Exception:  # noqa: BLE001 - best effort, the endpoints still work on demand
                pass

    for mode in ("casual", "analyst"):
        persona = Persona(mode=mode, language="en")
        await asyncio.gather(*(one(_explained(match, m, persona)) for m in _moments(match)))
        await one(_reel(match, None, persona))
        # "Highlights so far" only changes when a shot happens, so one reel per moment covers every click.
        for m in _moments(match):
            await one(_reel(match, m["t"], persona))


@app.get("/api/matches/{match_id}/moments/{moment_id}/explain")
async def explain_moment(
    request: Request, match_id: str, moment_id: str, mode: str = "casual", lang: str = "en",
    depth: Literal["full", "quick", "short"] = Query(default="full", description="full: the whole build-up; quick: key pass, shot and verdict; short: key pass and shot"),
) -> dict:
    """The explainer agent breaks one moment down into beats for the replay telestrator."""
    ratelimit.check(request, "ai")
    match = _match(match_id)
    moment = next((m for m in _moments(match) if m["id"] == moment_id), None)
    if moment is None:
        raise HTTPException(404, f"Unknown moment {moment_id}")
    return await _explained(match, moment, Persona(mode=mode, language=lang), depth)


@app.get("/api/matches/{match_id}/highlights")
async def highlights_reel(request: Request, match_id: str, upto: float | None = None, mode: str = "casual", lang: str = "en") -> dict:
    """Automated highlights package: the producer picks the clips, one explainer per clip runs in
    parallel, then the producer writes the intro and outro. `upto` = highlights so far (live)."""
    ratelimit.check(request, "ai")
    return await _reel(_match(match_id), upto, Persona(mode=mode, language=lang))


# ----------------------------------------------------------------------------- A2A
def _demo_match() -> Match:
    return _match(_store().list()[0]["match_id"])


async def _a2a_ask(question: str) -> str:
    match = _demo_match()
    insights, snapshots = await asyncio.to_thread(_full_pass, match)
    last = match.frames[-1]
    ctx = LiveContext(meta=match.meta, t=last.t, score=dict(last.score), snapshots=snapshots, events=list(match.events))
    out = await AskAgent(llm).answer(question[:300], ctx, Persona(mode="analyst"))
    tools = ", ".join(c["tool"] for c in out["tools"])
    return out["answer"] + (f"\n\n(tools used: {tools})" if tools else "")


async def _a2a_explain(text: str) -> str:
    match = _demo_match()
    minute = minute_of(text)
    moments = _moments(match)
    if not moments:
        return "No shots in this match yet."
    wanted = "goal" if "goal" in text.lower() else None
    pool = [m for m in moments if wanted is None or m["kind"] == wanted] or moments
    moment = min(pool, key=lambda m: abs(m["minute"] - (minute or m["minute"])))
    out = await _explained(match, moment, Persona(mode="analyst"))
    lines = [f"{moment['minute']}' {moment['kind']}: {out['headline']}"] + [f"- {b['text']}" for b in out["beats"]]
    if out["verdict"]:
        lines.append(out["verdict"])
    return "\n".join(lines)


async def _a2a_highlights(_: str) -> str:
    out = await _reel(_demo_match(), None, Persona())
    lines = [out["intro"]]
    for item in out["items"]:
        m = item["moment"]
        lines.append(f"- {m['minute']}' {m['kind'].upper()}: {item['headline']}. " + " ".join(b["text"] for b in item["beats"]))
    lines.append(out["outro"])
    return "\n".join(lines)


app.router.routes.extend(build_a2a_routes({"ask": _a2a_ask, "explain": _a2a_explain, "highlights": _a2a_highlights}))


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
    paused: bool = Query(default=False, description="start at kick-off, waiting for a play control"),
):
    await ws.accept()
    match = _store().get(match_id)
    if match is None:
        await ws.send_json({"type": "error", "message": f"Unknown match {match_id}"})
        await ws.close()
        return

    pipeline = LivePipeline(match, plugins.split(",") if plugins else None)
    engine = ReplayEngine(match, speed)
    engine.paused = paused
    orchestrator = Orchestrator(match.meta, llm)
    ask_agent = AskAgent(llm)
    commentary = CommentaryScheduler()
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
        # Replays are deterministic, so the same moment for the same persona reads the same for every
        # viewer: reuse the line (and, through the speech cache, its audio) instead of regenerating it.
        key = (match_id, round(insights[0].t, 1), insights[0].kind, insights[0].headline, p.model_dump_json())
        # During an outage drill every line must run through the (failing) agents, not come from the cache.
        out = None if orchestrator.outage else _narration_cache.get(key)
        cached = out is not None
        if out is None:
            out = await orchestrator.narrate(t, score, insights, snapshots, p)
            if out is not None and clean(out.get("trace", [])):
                _narration_cache[key] = out
                if len(_narration_cache) > NARRATION_CACHE_SIZE:
                    _narration_cache.pop(next(iter(_narration_cache)))
        if out is not None:
            await send({"type": "narration", **out, "cached": cached})

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
            elif kind == "drill":
                # Outage drill: fail the named agents on purpose; the broadcast must carry on through fallbacks.
                names = {a.name for a in orchestrator.chain}
                orchestrator.outage = {str(a) for a in msg.get("agents", []) if str(a) in names}
                await send({"type": "drill_ack", "agents": sorted(orchestrator.outage)})
            elif kind == "ask":
                question = str(msg.get("question", "")).strip()[:300]
                if question and not ratelimit.allow(ratelimit.client_ip(ws), "ask"):
                    await send({"type": "answer", "question": question, "answer": "Too many questions in a minute; try again shortly.",
                                "tools": [], "path": "rate_limited", "clock": "", "ms": 0})
                elif question:
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
                if seeked:
                    commentary.clear()
                pick = commentary.offer(result.insights, frame.t)
                if pick is not None:
                    task = asyncio.create_task(narrate(frame.t, dict(frame.score), [pick], pipeline.snapshots(), persona))
                    commentary.started(task)
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

    @app.middleware("http")
    async def no_stale_index(request, call_next):
        """The page itself must always be re-checked so visitors get the latest build;
        hashed assets under /assets can still be cached forever."""
        response = await call_next(request)
        if not request.url.path.startswith(("/api/", "/assets/", "/ws/")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
