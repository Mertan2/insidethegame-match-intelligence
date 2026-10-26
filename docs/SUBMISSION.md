# Submission kit

Paste-ready text for the Innovation Studio **Create project** form. Submissions close **Oct 27, 2026, 11:59 PM PT**.

## Project name

Inside the Game: Match Intelligence

## Category

Best Multi-Agent Orchestration (also eligible for the Grand Prize)

## Tagline (one line)

Every fan gets their own commentator: their club, their player, their language, spoken live. One data feed, millions of personal broadcasts, explained by a team of AI agents.

## Elevator pitch

A football broadcast is made once, for everyone, in one language. Live match data says *what* happened; fans,
studios and broadcasters want *why* it matters, instantly, each in their own way. Inside the Game makes one data
feed into a personal broadcast for every viewer: their club, their player, the one number they care about, their
language, spoken out loud, which also makes the match accessible to fans who cannot see the screen. Inside the Game turns synthetic, football-realistic tracking and events into explainable match
intelligence: deeper stats, a 3D ball-flight forecast that calls shots on target before they arrive, and a team of
specialised AI agents on Microsoft Agent Framework that commentates the whole match live, out loud, in the viewer's
language. Click any goal or chance and an explainer agent replays it like a TV analyst at the telestrator: the
move is drawn on the pitch, the replay freezes on the key pass and the shot, and the analyst says why it worked. One
click cuts an AI highlights package of the match so far: a producer agent picks the clips, explainers write every clip
in parallel, the producer writes the intro and outro, and it plays narrated. Built with Microsoft Agent Framework, Azure OpenAI (Microsoft Foundry
models), Azure AI Speech and Azure Container Apps.

## Description

**The problem.** A live feed is a stream of numbers. Turning it into a story ("that's their longest passing move of
the match", "it comes against the run of play", "the forecast called it on target 0.3 s before it arrived") takes a
studio team, and it is produced once, for everyone, in one language. A Premier League match is watched by hundreds
of millions of people who support different clubs, follow different players, speak different languages and watch
with different levels of sight and expertise. One broadcast cannot serve them all; a team of agents can.

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
2. **Interpret:** toggleable analytics plugins: possession, xG, pass quality (distance, accuracy, difficulty
   rating), ball and shot speed, player tags at sprint and distance thresholds, momentum, a control-vs-chaos index,
   fatigue from tracking alone, and the key moments (build-up, key pass, shot context) behind every shot.
3. **Explain:** a physics ball-flight forecast (gravity, drag, spin, bounce) predicts landing points and goal-line
   crossings and is scored against reality (about 0.1–0.2 m error one second ahead); the agents explain why each
   moment matters.
4. **Render:** a **Studio mode** that shows the output as a broadcast or stream would carry it (full-screen
   pitch, score bug, graphics cues, the commentary as a lower-third caption, the agent strip), 2D tactical and 3D
   views, broadcast graphics (lower thirds, "ON TARGET" calls, fun-fact cards) also exported as a timed,
   machine-readable cue timeline for a graphics engine, and a Data screen showing the raw feed, live charts and a
   22-player tracking table.
5. **Personalise:** casual vs analyst, favourite club, a player-focus mode (camera, stats and commentary follow one
   player), a metric-focus mode (the one number you care about, live and in the commentary), 7 languages, spoken by
   neural voices.

**Brief coverage, item by item.**
- **(ii) Real-time match intelligence.** *Player identification:* live name tags on the pitch, triggered when a
  player passes a sprint threshold (25 km/h, with the speed) or a distance threshold (each kilometre covered).
  *Pass quality:* every pass gets distance, outcome/accuracy and a difficulty rating (length, pressure, weak foot,
  progression). *Speed metrics:* live ball speed and every shot's speed, with the fastest shot of the match called.
  *Auto-eventing:* speed, distance, sprints, fatigue and ball speed are computed from the raw tracking stream, not
  from tagged events, so a tracking model's output can drive them with no manual tagging; there is no video in the
  synthetic data, so no vision model.
- **(iii) Narrative generation.** Play-by-play, fun facts (longest move, fastest shot, braces, headers, weak-foot
  goals, distance milestones), player-performance context in the player-focus mode, running, half-time and
  full-time recaps, and a narrated highlights package.
- **(iv) Explainability.** A control-vs-chaos index and momentum (game rhythm), pressure and tactical-pressure
  changes in the tactics agent's "why", and the telestrated explain-this-moment replay (how the ball was won, which
  pass took defenders out, the space at the shot, the verdict).
- **(v) Data innovation.** Our own synthetic generator: 22 players and the ball in 3D at 10 Hz with left/right
  foot positions from a gait model, preferred and weak feet, headers and crosses, fatigue that slows sprints, plus
  the full event stream (passes, shots, tackles, possession changes, pressure events, restarts, match metadata).
  Any seed and length; a 90-minute match in about 25 s.
- **(vi) Multi-language storytelling.** Commentary, answers, explanations and highlights in 7 languages (en, tr,
  es, fr, de, pt, ar), spoken by a neural voice in each.
- **Overlays for a rendering partner.** `GET /api/matches/{id}/overlays` returns the timed, machine-readable cue
  timeline (`t_in`, `t_out`, slot, template, data) to synchronise graphics with the live feed.
- **Personalisation.** Fan / Broadcaster / Analyst modes, casual vs tactical style, favourite club, favourite player
  with a player-focused mode (camera, stats and commentary follow one player), a **metric-focus mode** (pick the
  one performance metric you care about, such as sprint distance or completed passes: a live ranking stays on
  screen and the commentary keeps that number in), and language.

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
- **Recovering from failure, shown live.** Every agent runs with a timeout and a deterministic template fallback;
  each narration carries a trace of which agent ran, by which path and how long it took (shown live in the Agent
  team panel and in analyst mode), so one failing model call never silences the broadcast. The **outage drill**
  in the agent panel kills any agent in the chain on demand: the chain routes around it, the trace records the
  fallback and every line still goes out. Judges can try it, not just read about it.
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
- **GitHub:** public repository with GitHub Actions CI (56 tests, frontend build, Docker build and container smoke
  test).

**Why it matters.** One engine serves a studio analyst, a streaming overlay and a casual fan, each in their own
language and style, from a single data feed: commentary that scales to every viewer instead of one broadcast for
all. Spoken output makes the match accessible to blind and low-vision fans and to fans who do not speak the
broadcast language. The overlay timeline, Studio mode and WebSocket protocol are built to plug into a production
graphics path, and the A2A endpoint lets a broadcaster's own agents use the analyst as a service.

**Data innovation.** Most entries read the organiser's event file. We wrote a football-realistic generator: 22
players and the ball in 3D at 10 Hz, left and right foot positions from a gait model, preferred and weak feet,
headers and crosses, fatigue that slows sprints, and the full event stream, for any seed and length. The tracking
is what makes the explainer's telestration, the ball-flight forecast and the auto-computed speed and distance
metrics possible.

## Links

- Live demo: https://insidethegame.delightfulforest-cce043aa.swedencentral.azurecontainerapps.io
- Code (public): https://github.com/Mertan2/insidethegame-match-intelligence
- Video (under 2:00): **[paste the YouTube URL after uploading demo/demo-trailer.mp4]**

## How to try it (testing instructions)

1. Open the live demo, pick **Fan**, **Broadcaster** or **Analyst** and a language, press **Kick off** (sound on;
   browsers only allow audio after that click).
2. **Watch** is the broadcast: when a goal or chance lands, press **Replay & explain** in the caption (or the marker
   on the key moments timeline): the explainer agent replays the move with telestration and talks you through it.
3. Press **Highlights so far** (or **Match highlights** at full time): a narrated package cut by the producer and
   explainer agents.
4. In the rail, set your club, follow a player, pick the metric you care about, switch language: the commentary
   and the screen change for you. **Studio** shows the broadcast full screen.
5. **Crew** shows each line's run through the agents. Press **kill tactics** in the outage drill: the next lines
   still arrive, with the fallback in the trace. The A2A agent card and endpoint are listed there.
6. Ask a question in **Ask the AI**; the tools it called are listed under the answer.
7. **Data** shows the raw feed, live charts and the tracking table. **Setup** has match and plugin controls.

No login is needed.

## Before submitting

- [x] Live app deployed on Azure Container Apps with the model and speech connected
- [x] Public GitHub repository
- [ ] Video uploaded to YouTube as **Public** (the rules ask for a public URL; Unlisted is not public) and its URL pasted above
- [ ] Project created on Innovation Studio with the text above, category chosen, all three links added
- [ ] Submitted by **Oct 27, 11:59 PM PT**
