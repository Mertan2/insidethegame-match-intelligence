// Mirrors backend/app/models.py and plugin payloads.

export type Side = "home" | "away";

export interface PlayerMeta {
  id: string;
  name: string;
  number: number;
  team: Side;
  role: "GK" | "DEF" | "MID" | "FWD";
  preferred_foot: "left" | "right";
}

export interface TeamMeta {
  side: Side;
  name: string;
  short: string;
  color: string;
}

export interface MatchMeta {
  match_id: string;
  seed: number;
  minutes: number;
  fps: number;
  teams: Record<Side, TeamMeta>;
  players: PlayerMeta[];
  final_score: Record<Side, number>;
}

export interface Frame {
  f: number;
  t: number;
  ball: [number, number, number];
  players: [string, number, number][];
  /** (id, left x/y/z, right x/y/z) foot positions in metres */
  feet?: [string, number, number, number, number, number, number][] | null;
  owner: string | null;
  score: Record<Side, number>;
}

export interface MatchEvent {
  id: number;
  t: number;
  type: string;
  team: Side | null;
  player_id: string | null;
  x: number | null;
  y: number | null;
  data: Record<string, unknown>;
}

export interface PluginInfo {
  name: string;
  description: string;
  default_enabled: boolean;
}

export interface AgentInfo {
  name: string;
  role: string;
}

export interface Persona {
  mode: "casual" | "analyst";
  language: string;
  favorite_team: Side | null;
  favorite_player: string | null;
}

export interface TeamStats {
  passes: number;
  passes_completed: number;
  pass_accuracy_pct: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  xg: number;
  tackles: number;
  tackles_won: number;
  interceptions: number;
  pressures: number;
  possession_pct: number;
  aerial_passes: number;
}

export interface PlayerStats {
  player_id: string;
  name: string;
  team: Side;
  distance_m: number;
  top_speed_kmh: number;
  passes: number;
  passes_completed: number;
  shots: number;
  xg: number;
  preferred_foot: "left" | "right";
  left_foot: number;
  right_foot: number;
  headers: number;
  fatigue_pct: number | null;
  weak_foot_pct: number;
  weak_foot_success_pct: number | null;
}

export interface StatsPayload {
  teams: Record<Side, TeamStats>;
  players: PlayerStats[];
}

export interface ForecastPayload {
  active: boolean;
  speed_kmh?: number;
  trajectory?: [number, number, number][];
  apex_m?: number;
  landing?: { x: number; y: number; in_s: number } | null;
  goal_crossing?: { goal: Side; y: number; z: number; in_s: number; on_target: boolean } | null;
  accuracy?: { horizon_s: number; samples: number; mean_error_m: number | null };
}

export interface MomentumPayload {
  momentum: number;
  chaos_index: number;
  regime: "chaos" | "control" | "balanced";
  possession_changes_per_min: number;
  passes_last_min: Record<Side, number>;
}

export interface SpeedPayload {
  ball_speed_kmh: number;
  max_shot_kmh: number;
  last_shot: { t: number; player: string; speed_kmh: number } | null;
  tags: { t: number; player_id: string; name: string; speed_kmh: number }[];
}

export interface PassRecord {
  t: number;
  passer: string;
  receiver: string | null;
  team: Side;
  distance_m: number;
  difficulty: number;
  kind: string;
  outcome: string;
  progress_m: number;
}

export interface PassQualityPayload {
  recent: PassRecord[];
  teams: Record<Side, { accuracy_pct: number; avg_difficulty: number; progressive_passes: number }>;
}

export interface PluginPayloads {
  stats?: StatsPayload;
  ball_forecast?: ForecastPayload;
  momentum?: MomentumPayload;
  speed_metrics?: SpeedPayload;
  pass_quality?: PassQualityPayload;
  overlays?: { active: OverlayCue[] };
}

export interface Narration {
  t: number;
  clock: string;
  kind: string;
  importance: number;
  team: Side | null;
  player_id: string | null;
  headline: string;
  text: string;
  why: string[];
  facts: string[];
  language: string;
  requested_language: string;
  mode: string;
  trace: { agent: string; path?: string; status?: string; ms?: number; llm_error?: string }[];
}

export interface OverlayCue {
  id: number;
  t_in: number;
  t_out: number;
  slot: "lower_third" | "top_bug" | "side_panel";
  template: string;
  priority: number;
  team: Side | null;
  team_name: string;
  player_id: string | null;
  player: string | null;
  score: Record<Side, number>;
  data: Record<string, unknown>;
}

export interface SeriesPoint {
  t: number;
  possHome: number | null;
  xgHome: number;
  xgAway: number;
  momentum: number;
  ballKmh: number;
  goalsHome: number;
  goalsAway: number;
}

export interface Answer {
  question: string;
  answer: string;
  tools: { tool: string; args: Record<string, unknown> }[];
  path: string;
  clock: string;
  ms: number;
}

export interface Recap {
  title: string;
  paragraphs: string[];
  language: string;
  requested_language: string;
  path: string;
}
