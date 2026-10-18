# Submission kit

Draft text for the Innovation Studio project page and the demo video. Remaining **[TODO]** markers are
the video and anything only you can confirm.

## Project name

Inside the Game: Match Intelligence

## Elevator pitch (short)

A live match-intelligence engine that turns raw synthetic football tracking into explained moments.
It derives deeper stats, forecasts the ball's 3D flight before it lands, and has a team of AI agents
narrate why each moment matters, tailored to every fan.

## Description

**Problem.** Live data feeds say *what* happened: a pass, a shot, 58% possession. Broadcasters and fans
want *why* it matters, delivered instantly, for very different audiences (an analyst and a casual fan
watching the same match).

**What we built.** A pipeline covering the hackathon's five stages:

1. **Ingest.** Our own agent-based simulator generates football-realistic data: 22 players and the ball in
   3D at 10 Hz, **left/right foot tracking** from a gait model, preferred foot per player, and a full event
   stream (passes, shots, tackles, pressure, possession changes, restarts). A replay engine streams it like
   a live feed with pause, seek and up to 32x speed.
2. **Interpret.** Toggleable analytics plugins derive deeper data from the raw feed: possession, xG,
   pass difficulty rating (including weak-foot use), ball and shot speed, sprint detection, momentum, and a
   "control vs chaos" index.
3. **Explain.** A physics-based **3D ball forecast** predicts flight path, landing point and whether a shot
   is on target, often before the ball arrives. It is scored against reality (about 0.1–0.2 m error one
   second ahead). Multiple agents then explain the moment, not just report it.
4. **Render.** A bird's-eye 2D tactical view, a 3D match view with a follow camera, and **broadcast overlay
   cues** (timed, machine-readable graphics instructions, also exported as a timeline via API for a
   graphics engine).
5. **Personalize.** Casual vs analyst modes, favourite club, a **player-focus mode** (camera, stats and
   commentary follow one player), and language selection.

**See the data live.** A DATA tab shows the raw feed as it streams: throughput, xG race, possession,
momentum and ball-speed charts building second by second, a 22-player tracking table with live speed and
foot heights, and the event stream.

**Ask the AI.** Viewers ask anything, in any language. An agent with Azure OpenAI function calling picks
live-data tools (match state, team stats, a player, recent events, top players, ball forecast) and answers
only from what they return; the tools it used are shown under each answer.

**Agents (Microsoft Agent Framework).** A workflow of specialised agents shares one blackboard:
- *Stats agent* (deterministic): picks the moment and the grounded facts, so the AI can't invent numbers.
- *Tactics agent*: explains why it matters (momentum, chaos, pressure, forecast).
- *Narrator agent*: writes the live commentary line.
- *Persona agent*: adapts tone, focus and language to the viewer.
- *Recap agent*: writes the automated full-time report.
- *Ask agent*: answers viewer questions with function calling over live match data.

Each agent has a timeout and a deterministic fallback, and every narration carries a trace of which agent
ran how, so the live feed never goes silent if a model call fails.

**Microsoft technology**
- Microsoft Agent Framework: agents and workflow orchestration.
- Microsoft Foundry / Azure OpenAI: `gpt-4.1-mini` (Sweden Central) powers the tactics, narrator, persona and recap
  agents; verified live in English, Turkish and Spanish with about 1 s per agent.
- Azure Container Apps: single-container deployment (UI, API and WebSocket), image built in Azure Container
  Registry, model key stored as a Container Apps secret. Live: https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io
- GitHub: public repository with GitHub Actions CI (tests, frontend build, Docker build and smoke test).
  **[TODO: mention GitHub Copilot only if you used it]**

**Impact.** The same engine serves a studio analyst, a streaming overlay and a casual fan, in their own
language, from one data feed. The overlay timeline and WebSocket protocol are designed to plug into a
production graphics path.

## Links

- Repo: https://github.com/Mertan2/insidethegame-match-intelligence
- Demo: https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io
- Video: **[TODO: YouTube/Vimeo URL]**

## Demo video script (≤ 2:00)

No copyrighted music or third-party logos. Record at 1080p; use 4x–8x replay speed so key moments come quickly.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:12 | 2D + 3D views side by side, match running | "Live data tells you what happened. We built a system that tells you *why*, for every fan." |
| 0:12–0:30 | 3D view zoomed on players, legs moving; toggle plugins on/off | "Everything starts from raw tracking: 22 players, the ball in 3D, even each player's feet. Analytics plugins derive deeper stats and can be switched on or off live." |
| 0:30–0:52 | A shot: dashed forecast arc, "ON TARGET in 0.4s" overlay, then save or goal | "Our physics model forecasts the ball's flight. Here it called the shot on target before it arrived, accurate to about 15 centimetres." |
| 0:52–1:15 | Analyst mode: narration with "why" bullets and agent trace | "A team of AI agents on Microsoft Agent Framework explains the moment: the stats agent grounds the facts, tactics explains why, the narrator writes the line." |
| 1:15–1:35 | Switch to casual mode, Turkish, follow a player; camera follows, focus panel | "The persona agent tailors it: casual or analyst, any language, or follow one player all match." |
| 1:35–1:50 | Click Generate recap at full time | "At full time the recap agent writes the match report automatically." |
| 1:50–2:00 | Architecture slide or repo page | "Inside the Game: Agent Framework, Foundry and Azure Container Apps. Explainable match intelligence for every fan." |

## Before submitting

- [x] `backend/.env` filled; `scripts/check_foundry.py` passes; translation shows in the UI
- [x] Deployed on Azure Container Apps (check the URL once more in a private window before submitting)
- [ ] Video recorded, under 2:00, uploaded as public/unlisted on YouTube or Vimeo
- [ ] TODO markers above resolved
- [ ] Submitted by **Oct 27, 11:59 PM PT**
