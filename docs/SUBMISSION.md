# Submission kit

Paste-ready text for the Innovation Studio **Create project** form. Submissions close **Oct 27, 2026, 11:59 PM PT**.

## Project name

Inside the Game: Match Intelligence

## Category

Best Multi-Agent Orchestration (also eligible for the Grand Prize)

## Tagline (one line)

A team of AI agents that watches every event of a football match, explains it live and cuts a narrated, telestrated highlights package in one click, for fans, broadcasters and analysts.

## Elevator pitch

Live match data says *what* happened; fans, studios and broadcasters want *why* it matters, instantly, for very
different audiences. Inside the Game turns synthetic, football-realistic tracking and events into explainable match
intelligence: deeper stats, a 3D ball-flight forecast that calls shots on target before they arrive, and a team of
specialised AI agents on Microsoft Agent Framework that commentates the whole match live, out loud, in the viewer's
language. Click any goal or chance and an explainer agent replays it like a TV analyst at the telestrator: the
move is drawn on the pitch, the replay freezes on the key pass and the shot, and the analyst says why it worked. One
click cuts an AI highlights package of the match so far: a producer agent picks the clips, explainers write every clip
in parallel, the producer writes the intro and outro, and it plays narrated. Built with Microsoft Agent Framework, Azure OpenAI (Microsoft Foundry
models), Azure AI Speech and Azure Container Apps.

## Description

**The problem.** A live feed is a stream of numbers. Turning it into a story ("that's their longest passing move of
the match", "it comes against the run of play", "the forecast called it on target 0.3 s before it arrived") normally
takes a studio team, and it is produced once for everyone.

**What it does.** Open the app, choose a language and who is watching (**Fan**, **Broadcaster** or **Analyst**:
each gets its own commentary style and screen), press **Kick off**. The match plays
and an AI commentary team talks you through it continuously: play-by-play of what is on screen, fun facts as they
happen, running and half-time/full-time recaps, and every goal and big chance first. You can ask it anything
mid-match ("who is tiring?", "why are they dominating?") and see exactly which live-data tools it used to answer.
Every shot and goal lands on a **key moments** timeline: click one to **explain this moment** (a telestrated,
narrated replay grounded in the tracking: how the ball was won, the passes that took defenders out, the space at the
shot), or press **Highlights so far** for an automated, narrated highlights package with no spoilers past the live
clock.

**The pipeline (the brief's five stages).**
1. **Ingest:** an agent-based simulator produces football-realistic data (22 players and the ball in 3D at 10 Hz,
   left/right foot positions, headers, crosses, fatigue, a full event stream), replayed like a live feed.
2. **Interpret:** toggleable analytics plugins: possession, xG, pass difficulty (incl. weak-foot use), ball and shot
   speed, sprint tags, momentum, a control-vs-chaos index, fatigue from tracking alone.
3. **Explain:** a physics ball-flight forecast (gravity, drag, spin, bounce) predicts landing points and goal-line
   crossings and is scored against reality (about 0.1–0.2 m error one second ahead); the agents explain why each
   moment matters.
4. **Render:** 2D tactical and 3D views, broadcast graphics (lower thirds, "ON TARGET" calls, fun-fact cards) also
   exported as a timed, machine-readable cue timeline for a graphics engine, and a DATA tab showing the raw feed,
   live charts and a 22-player tracking table.
5. **Personalise:** casual vs analyst, favourite club, a player-focus mode (camera, stats and commentary follow one
   player), 7 languages, spoken by neural voices.

**Multi-agent orchestration (Microsoft Agent Framework).**
- **Distinct roles.** A deterministic *broadcast director* watches every event and frame and writes briefs
  (play-by-play, fun facts, recaps). The *stats agent* picks the moment and the grounded facts. The *tactics agent*
  explains why it matters. The *narrator agent* writes the line. The *persona agent* adapts tone, focus and language
  to the viewer. The *recap agent* writes match reports. The *ask agent* answers viewer questions with function
  calling over six live-data tools. The *explainer agent* breaks a moment into spoken beats tied to the replay's
  freeze-frames. The *producer agent* cuts the highlights package.
- **A2A.** The match analyst is published as an A2A agent (agent card plus JSON-RPC endpoint, via Agent
  Framework's `A2AExecutor`), so a broadcaster's own agent can ask it questions, have it explain a moment or
  fetch the highlights package: the agent team is a building block for other agents, not just a UI.
- **Fan-out / fan-in.** For highlights the producer ranks the moments, launches one explainer per clip in parallel,
  then writes the intro and outro over what they returned; every step is traced and falls back on its own.
- **Shared state and handoffs.** The live chain is an Agent Framework `Workflow` with one executor per agent; agents
  coordinate through a blackboard in workflow shared state, each writing its own slot and handing off to the next. A
  commentary scheduler decides what is said when: key moments jump the queue, routine briefs are paced for a voice
  to read, stale play is never described.
- **Grounding.** Numbers come only from the deterministic stats layer; language-model agents phrase, explain and
  translate, and are told the score and what each goal did ("equaliser", "takes the lead") so they cannot invent it.
- **Recovering from failure.** Every agent runs with a timeout and a deterministic template fallback; each narration
  carries a trace of which agent ran, by which path and how long it took (shown live in the Agent team panel and in analyst mode), so one failing
  model call never silences the broadcast.
- **Observable in production.** Every narration, agent step (path, fallback, latency), Ask question, tool call and
  voice request is an OpenTelemetry span in Azure Application Insights, with the Azure OpenAI and Speech calls
  underneath as dependencies, so you can see which agent is slow or falling back on the live deployment.
- **End-to-end outcome.** From raw tracking to spoken, personalised, explained commentary for the whole match, which
  no single agent could produce live and grounded at the same time.

**Microsoft and Azure technology.**
- **Microsoft Agent Framework:** agents, the live narration workflow, and the A2A server (`A2AExecutor`).
- **Azure OpenAI (`gpt-4.1-mini`, Microsoft Foundry model):** tactics, narrator, persona, recap and ask agents,
  including function calling.
- **Azure AI Speech:** neural-voice spoken commentary and answers in 7 languages.
- **Azure Container Apps + Azure Container Registry:** single container serving the UI, REST and WebSocket feed;
  model, speech and telemetry keys are Container Apps secrets.
- **Azure Monitor Application Insights:** OpenTelemetry traces of the agent workflow, tools and voice.
- **Production readiness:** per-client rate limits on paid endpoints, cross-viewer caching of commentary and
  replays, background cache warm-up after a restart, secrets in Container Apps, CI on every push.
- **GitHub:** public repository with GitHub Actions CI (54 tests, frontend build, Docker build and container smoke
  test).

**Why it matters.** One engine serves a studio analyst, a streaming overlay and a casual fan, each in their own
language and style, from a single data feed, and the overlay timeline and WebSocket protocol are built to plug into
a production graphics path.

## Links

- Live demo: https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io
- Code (public): https://github.com/Mertan2/insidethegame-match-intelligence
- Video (under 2:00): **[paste the YouTube/Vimeo URL after uploading demo/insidethegame_demo.mp4]**

## How to try it (testing instructions)

1. Open the live demo, pick a language and **Fan**, **Broadcaster** or **Analyst**, press **Kick off** (sound on;
   browsers only allow audio after that click).
2. When a ⚽ or 🧤 appears on the **Key moments** timeline, click it: the explainer agent replays the move with
   telestration and talks you through it.
3. Press **🎬 Highlights so far** (or **Match highlights** at full time): a narrated package cut by the producer and
   explainer agents.
4. Watch the **Agent team · live** panel (Broadcaster or Analyst) for each line's run through the agents.
5. Ask a question in **Ask the AI**; the tools it called are listed under the answer.
6. In Analyst, the **DATA** tab shows the raw feed, live charts and tracking table. **⚙ Setup** has match and plugin
   controls.

No login is needed.

## Before submitting

- [x] Live app deployed on Azure Container Apps with the model and speech connected
- [x] Public GitHub repository
- [ ] Video uploaded to YouTube or Vimeo (Public or Unlisted) and its URL pasted above
- [ ] Project created on Innovation Studio with the text above, category chosen, all three links added
- [ ] Submitted by **Oct 27, 11:59 PM PT**
