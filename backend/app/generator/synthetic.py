"""Agent-based synthetic match simulator.

Produces football-realistic tracking (22 players + ball in x/y/z at `fps`) and an
event stream (passes, shots, tackles, pressure, possession changes, restarts).
Ball flight uses the same physics as the forecast plugin, with spin the tracking
feed does not expose, so forecasts are realistic rather than perfect.

Simplifications: teams do not swap ends at half time, no offside, no fouls/cards.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from .. import physics
from ..models import Event, Frame, Match, MatchMeta, PlayerMeta, TeamMeta

L, W = physics.PITCH_LENGTH, physics.PITCH_WIDTH

FIRST_NAMES = [
    "Arlo", "Bram", "Cael", "Dario", "Emre", "Finn", "Goran", "Hugo", "Ilyas", "Jonah",
    "Kai", "Luca", "Mateo", "Nico", "Oren", "Pavel", "Quinn", "Rafa", "Soren", "Teo",
    "Umar", "Vito", "Wes", "Xavi", "Yusuf", "Zane", "Ansel", "Bodhi", "Cyrus", "Deniz",
]
LAST_NAMES = [
    "Ashdown", "Brightwell", "Calder", "Dunmore", "Ellery", "Fairholt", "Greaves", "Halloran",
    "Ingram", "Jessop", "Kestrel", "Lowther", "Marlow", "Northcott", "Oakes", "Penrose",
    "Quayle", "Redfern", "Stanmore", "Thorne", "Underhill", "Vance", "Whitlock", "Yardley",
]

# Base positions in the *attacking frame*: own goal at x=0, attacking towards x=105.
FORMATIONS = {
    "4-3-3": [
        ("GK", 4, 34),
        ("DEF", 24, 8), ("DEF", 21, 25), ("DEF", 21, 43), ("DEF", 24, 60),
        ("MID", 40, 18), ("MID", 36, 34), ("MID", 40, 50),
        ("FWD", 58, 10), ("FWD", 62, 34), ("FWD", 58, 58),
    ],
    "4-4-2": [
        ("GK", 4, 34),
        ("DEF", 23, 9), ("DEF", 20, 26), ("DEF", 20, 42), ("DEF", 23, 59),
        ("MID", 40, 10), ("MID", 37, 27), ("MID", 37, 41), ("MID", 40, 58),
        ("FWD", 58, 27), ("FWD", 58, 41),
    ],
}

JOG, RUN, SPRINT = 3.5, 6.0, 7.8  # m/s
HEADER_MIN_Z, HEADER_MAX_Z = 1.4, 2.6  # ball height an outfield player heads rather than controls


@dataclass
class SimPlayer:
    meta: PlayerMeta
    base: np.ndarray  # attacking frame
    pos: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2))
    pace: float = 1.0  # individual top-speed multiplier
    tackle_cooldown_until: float = 0.0
    # Gait state for foot tracking.
    heading: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0]))
    gait_phase: float = 0.0
    kick_foot: str | None = None  # foot planted on the ball during a kick
    kick_point: np.ndarray | None = None
    kick_until: float = 0.0

    @property
    def id(self) -> str:
        return self.meta.id

    @property
    def team(self) -> str:
        return self.meta.team


def to_world(team: str, ax: float, ay: float) -> np.ndarray:
    return np.array([ax, ay]) if team == "home" else np.array([L - ax, W - ay])


def to_attacking(team: str, wx: float, wy: float) -> np.ndarray:
    return np.array([wx, wy]) if team == "home" else np.array([L - wx, W - wy])


def goal_x_for(team: str) -> float:
    """x of the goal this team attacks."""
    return L if team == "home" else 0.0


def other(team: str) -> str:
    return "away" if team == "home" else "home"


class MatchSimulator:
    def __init__(self, seed: int = 7, minutes: int = 20, fps: int = 10, match_id: str | None = None):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.seed = seed
        self.minutes = minutes
        self.fps = fps
        self.dt = 1.0 / fps
        self.substeps = 5
        self.match_id = match_id or f"synthetic-{seed}"

        self.teams = {
            "home": TeamMeta(side="home", name="Northbridge FC", short="NBR", color="#e4572e"),
            "away": TeamMeta(side="away", name="Riverside Athletic", short="RVA", color="#29a3e0"),
        }
        self.players: list[SimPlayer] = []
        used_names: set[str] = set()
        traits = random.Random(seed * 7919 + 1)  # independent stream for player attributes
        for team, formation in (("home", "4-3-3"), ("away", "4-4-2")):
            for i, (role, bx, by) in enumerate(FORMATIONS[formation]):
                name = self._unique_name(used_names)
                foot = "left" if traits.random() < 0.22 else "right"  # ~1 in 5 players is left-footed
                meta = PlayerMeta(
                    id=f"{team[0]}{i + 1}", name=name, number=1 if role == "GK" else i + 1, team=team, role=role,
                    preferred_foot=foot,
                )
                base = np.array([bx, by], dtype=float)
                pace = 0.85 if role == "GK" else self.rng.uniform(0.88, 1.1)
                self.players.append(
                    SimPlayer(
                        meta=meta, base=base, pos=to_world(team, bx, by), pace=pace,
                        gait_phase=self.rng.uniform(0, 2 * math.pi),
                    )
                )

        self.t = 0.0
        self.frame_idx = 0
        self.ball_pos = np.array([L / 2, W / 2, 0.0])
        self.ball_vel = np.zeros(3)
        self.ball_spin: np.ndarray | None = None
        self.owner: SimPlayer | None = None
        self.possession_team = "home"
        self.last_touch: SimPlayer | None = None
        self.kicker: SimPlayer | None = None
        self.kick_time = -10.0
        self.kick_origin = np.array([L / 2, W / 2])
        self._path_cache: tuple[int, list] | None = None
        self.intended_receiver: SimPlayer | None = None
        self.pending_pass: dict | None = None
        self.pending_shot: dict | None = None
        self.hold_until = 0.0
        self.dead_until = 0.0
        self.last_pressure_t: dict[str, float] = {}
        self.score = {"home": 0, "away": 0}
        self.events: list[dict] = []
        self.frames: list[Frame] = []

    # ------------------------------------------------------------------ helpers
    def _unique_name(self, used: set[str]) -> str:
        while True:
            name = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            if name not in used:
                used.add(name)
                return name

    def _emit(self, type_: str, player: SimPlayer | None = None, team: str | None = None, **kw) -> dict:
        ev = {
            "id": len(self.events),
            "t": round(self.t, 2),
            "frame": self.frame_idx,
            "type": type_,
            "team": team or (player.team if player else None),
            "player_id": player.id if player else None,
            "x": kw.pop("x", round(float(self.ball_pos[0]), 2)),
            "y": kw.pop("y", round(float(self.ball_pos[1]), 2)),
            "end_x": kw.pop("end_x", None),
            "end_y": kw.pop("end_y", None),
            "data": kw,
        }
        self.events.append(ev)
        return ev

    def _team(self, team: str) -> list[SimPlayer]:
        return [p for p in self.players if p.team == team]

    def _nearest(self, players: list[SimPlayer], point: np.ndarray) -> tuple[SimPlayer, float]:
        best = min(players, key=lambda p: float(np.linalg.norm(p.pos - point[:2])))
        return best, float(np.linalg.norm(best.pos - point[:2]))

    def _set_owner(self, p: SimPlayer, cause: str) -> None:
        if p.team != self.possession_team:
            self._emit("possession_change", p, cause=cause, from_team=self.possession_team)
            self.possession_team = p.team
        self.owner = p
        self.last_touch = p
        self.intended_receiver = None
        self.ball_vel = np.zeros(3)
        self.ball_spin = None
        self.ball_pos = np.array([p.pos[0], p.pos[1], 0.0])
        gk = p.meta.role == "GK"
        self.hold_until = self.t + (self.rng.uniform(1.5, 3.0) if gk else self.rng.uniform(0.6, 2.2))

    # ------------------------------------------------------------- restarts
    def _kickoff(self, team: str) -> None:
        for p in self.players:
            ax = min(p.base[0] * 0.85, 50.0)
            p.pos = to_world(p.team, ax, p.base[1])
            p.vel = np.zeros(2)
        kicker = next(p for p in self._team(team) if p.meta.role == "FWD")
        kicker.pos = np.array([L / 2, W / 2])
        self.ball_pos = np.array([L / 2, W / 2, 0.0])
        self.possession_team = team
        self._set_owner(kicker, "kickoff")
        self._emit("kickoff", kicker)
        self.dead_until = self.t + 1.0
        self.hold_until = self.dead_until + 0.3

    def _restart(self, type_: str, team: str, spot: np.ndarray, pause: float = 1.5) -> None:
        if type_ == "goal_kick":
            taker = next(p for p in self._team(team) if p.meta.role == "GK")
        else:
            taker, _ = self._nearest([p for p in self._team(team) if p.meta.role != "GK"], spot)
        taker.pos = spot.copy()
        taker.vel = np.zeros(2)
        self.ball_pos = np.array([spot[0], spot[1], 0.0])
        self._resolve_pending("out")
        self._emit(type_, taker, x=round(float(spot[0]), 2), y=round(float(spot[1]), 2))
        self._set_owner(taker, type_)
        self.dead_until = self.t + pause
        self.hold_until = self.dead_until + 0.3

    def _resolve_pending(self, outcome: str, receiver: SimPlayer | None = None) -> None:
        if self.pending_pass is not None:
            self.pending_pass["data"]["outcome"] = outcome
            if receiver is not None:
                self.pending_pass["data"]["receiver_id"] = receiver.id
            self.pending_pass = None
        if self.pending_shot is not None and outcome in ("out", "off_target"):
            self.pending_shot["data"]["outcome"] = "off_target"
            self.pending_shot = None

    # ------------------------------------------------------------- movement
    def _move(self, p: SimPlayer, target: np.ndarray, speed: float) -> None:
        delta = target - p.pos
        dist = float(np.linalg.norm(delta))
        speed *= p.pace
        desired = np.zeros(2) if dist < 0.2 else delta / dist * min(speed, dist / self.dt)
        p.vel = p.vel + (desired - p.vel) * min(1.0, 4.0 * self.dt)
        p.pos = np.clip(p.pos + p.vel * self.dt, [0.5, 0.5], [L - 0.5, W - 0.5])

    def _ball_target_for(self, p: SimPlayer) -> np.ndarray:
        """Earliest point on the predicted ball path the player can reach (ball is free)."""
        # The ball's path is the same for every chaser this frame: simulate it once.
        if self._path_cache is None or self._path_cache[0] != self.frame_idx:
            path = physics.simulate(self.ball_pos, self.ball_vel, duration=3.0, dt=0.05, spin=self.ball_spin)
            self._path_cache = (self.frame_idx, path)
        path = self._path_cache[1]
        attacking_cross = (
            p is self.intended_receiver
            and self.pending_pass is not None
            and self.pending_pass["data"].get("kind") == "cross"
        )
        if attacking_cross:  # attack the ball as it drops through head height
            for (_, prev), (t, bp) in zip(path, path[1:]):
                if 1.6 <= bp[2] <= 2.4 and bp[2] < prev[2] and np.linalg.norm(bp[:2] - p.pos) / SPRINT <= t:
                    return bp[:2]
        for t, bp in path[1:]:
            if bp[2] < 1.8 and np.linalg.norm(bp[:2] - p.pos) / SPRINT <= t:
                return bp[:2]
        return path[-1][1][:2]

    def _update_players(self) -> None:
        ball_xy = self.ball_pos[:2]
        chasers: set[str] = set()
        if self.owner is None and self.t >= self.dead_until:
            for team in ("home", "away"):
                outfield = [p for p in self._team(team) if p.meta.role != "GK" and p is not self.kicker]
                chasers.add(self._nearest(outfield, self.ball_pos)[0].id)
            if self.intended_receiver is not None:
                chasers.add(self.intended_receiver.id)
        pressers: list[str] = []
        if self.owner is not None and self.t >= self.dead_until:
            opp = [p for p in self._team(other(self.owner.team)) if p.meta.role != "GK"]
            opp.sort(key=lambda p: float(np.linalg.norm(p.pos - ball_xy)))
            pressers = [p.id for p in opp[:2]]

        for p in self.players:
            if p is self.owner:
                continue
            ball_a = to_attacking(p.team, *ball_xy)
            in_possession = self.possession_team == p.team
            if p.id in chasers:
                self._move(p, self._ball_target_for(p), SPRINT)
                continue
            if p.id in pressers:
                # First presser closes down to ~1.5 m, second covers at ~6 m on the goal side.
                own_goal = np.array([L - goal_x_for(p.team), W / 2])
                to_goal = own_goal - ball_xy
                to_goal /= max(1e-6, float(np.linalg.norm(to_goal)))
                gap = 1.5 if p.id == pressers[0] else 6.0
                self._move(p, ball_xy + to_goal * gap, RUN)
                continue
            if p.meta.role == "GK":
                gx = float(np.clip(p.base[0] + (ball_a[0] - 52.5) * 0.08, 1.0, 14.0))
                gy = float(np.clip(34 + (ball_a[1] - 34) * 0.15, physics.GOAL_Y_MIN, physics.GOAL_Y_MAX))
                if self.pending_shot is not None and self.pending_shot["team"] != p.team:
                    target = to_world(p.team, gx, 34.0)
                    target[1] = float(np.clip(self.pending_shot["data"]["_aim_y"], 28, 40))
                    self._move(p, target, 6.0)
                    continue
                self._move(p, to_world(p.team, gx, gy), JOG)
                continue
            push = {"DEF": 3.0, "MID": 6.0, "FWD": 8.0}[p.meta.role] if in_possession else -4.0
            ax = float(np.clip(p.base[0] + (ball_a[0] - 52.5) * 0.45 + push, 3.0, 102.0))
            ay = float(np.clip(p.base[1] + (ball_a[1] - 34.0) * 0.25, 2.0, W - 2.0))
            self._move(p, to_world(p.team, ax, ay), JOG if abs(ax - to_attacking(p.team, *p.pos)[0]) < 10 else RUN)

    # ------------------------------------------------------------- on-ball
    def _dribble(self, p: SimPlayer) -> None:
        goal = np.array([goal_x_for(p.team), W / 2])
        direction = goal - p.pos
        direction /= max(1e-6, float(np.linalg.norm(direction)))
        opp, d = self._nearest(self._team(other(p.team)), np.array([*p.pos, 0.0]))
        if d < 6.0:
            away = p.pos - opp.pos
            away /= max(1e-6, float(np.linalg.norm(away)))
            direction = direction * 0.6 + away * 0.4
            direction /= max(1e-6, float(np.linalg.norm(direction)))
        speed = 1.5 if p.meta.role == "GK" else self.rng.uniform(3.5, 5.5)
        self._move(p, p.pos + direction * speed, speed)
        self.ball_pos = np.array([*(p.pos + direction * 0.5), 0.0])
        self.ball_pos[:2] = np.clip(self.ball_pos[:2], [0.2, 0.2], [L - 0.2, W - 0.2])

    def _check_pressure_and_tackle(self, p: SimPlayer) -> bool:
        opp, d = self._nearest(
            [o for o in self._team(other(p.team)) if o.meta.role != "GK"], np.array([*p.pos, 0.0])
        )
        if d < 2.5 and self.t - self.last_pressure_t.get(p.id, -99) > 6.0:
            self.last_pressure_t[p.id] = self.t
            self._emit("pressure", opp, target_id=p.id, distance=round(d, 2))
        if d < 2.0 and self.t >= opp.tackle_cooldown_until and self.rng.random() < 0.025:
            success = self.rng.random() < 0.5
            self._emit("tackle", opp, target_id=p.id, success=success)
            if success:
                self._set_owner(opp, "tackle")
                return True
            opp.tackle_cooldown_until = self.t + 3.0
        return False

    def _decide(self, p: SimPlayer) -> None:
        goal = np.array([goal_x_for(p.team), W / 2])
        dist_goal = float(np.linalg.norm(goal - p.pos))
        if self._try_cross(p):
            return
        if p.meta.role != "GK" and dist_goal < 28:
            shot_prob = float(np.clip(0.9 - dist_goal / 22, 0.05, 0.6))
            if self.rng.random() < shot_prob:
                self._shoot(p, dist_goal)
                return
        opponents = self._team(other(p.team))
        candidates = []
        for mate in self._team(p.team):
            if mate is p or mate.meta.role == "GK":
                continue
            d = float(np.linalg.norm(mate.pos - p.pos))
            if not 5.0 <= d <= 50.0:
                continue
            gain = to_attacking(p.team, *mate.pos)[0] - to_attacking(p.team, *p.pos)[0]
            openness = min(float(np.linalg.norm(o.pos - mate.pos)) for o in opponents)
            score = 0.06 * gain + 0.15 * min(openness, 10) - 0.02 * d + self.rng.gauss(0, 0.4)
            candidates.append((score, mate, d))
        if not candidates:
            self.hold_until = self.t + 0.5
            return
        _, receiver, d = max(candidates, key=lambda c: c[0])
        self._pass(p, receiver, d)

    def _try_cross(self, p: SimPlayer) -> bool:
        """Wide in the final third: deliver an aerial ball for a teammate to attack with the head."""
        ax, ay = to_attacking(p.team, *p.pos)
        if ax < 65 or 20 <= ay <= 48 or self.rng.random() > 0.6:
            return False
        targets = [
            m for m in self._team(p.team)
            if m is not p and 78 < to_attacking(m.team, *m.pos)[0] < 101 and 18 < to_attacking(m.team, *m.pos)[1] < 50
        ]
        if not targets:
            return False
        receiver = self.rng.choice(targets)
        direction = receiver.pos - p.pos
        d = float(np.linalg.norm(direction))
        # Aim to land just beyond the attacker so the ball reaches them at head height on the way down.
        landing = receiver.pos + direction / d * 3.0 + self.np_rng.normal(0, 0.08 * d, 2)
        landing = np.clip(landing, [1, 1], [L - 1, W - 1])
        _, pressure_d = self._nearest(self._team(other(p.team)), np.array([*p.pos, 0.0]))
        foot = self._choose_foot(p, pressure_d)
        start = np.array([self.ball_pos[0], self.ball_pos[1], 0.03])
        vel = physics.aerial_launch_velocity(start, landing, self.rng.uniform(20, 28))
        ev = self._emit(
            "pass",
            p,
            end_x=round(float(landing[0]), 2),
            end_y=round(float(landing[1]), 2),
            kind="cross",
            intended_receiver_id=receiver.id,
            speed_kmh=round(float(np.linalg.norm(vel)) * 3.6, 1),
            distance=round(d, 1),
            pressure_distance=round(pressure_d, 2),
            body_part=f"{foot}_foot",
            weak_foot=foot != p.meta.preferred_foot,
            outcome=None,
        )
        self.pending_pass = ev
        self._kick(p, start, vel, foot)
        self.ball_spin = np.array([0.0, 0.0, self.rng.uniform(-10, 10)])
        self.intended_receiver = receiver
        return True

    def _pass(self, p: SimPlayer, receiver: SimPlayer, d: float) -> None:
        aerial = d > 28 or (d > 18 and self.rng.random() < 0.25)
        _, pressure_d = self._nearest(self._team(other(p.team)), np.array([*p.pos, 0.0]))
        travel = d / (18.0 if aerial else 14.0)
        target = receiver.pos + receiver.vel * travel * 0.8
        foot = self._choose_foot(p, pressure_d)
        noise = 0.03 * d * (1.6 if pressure_d < 3 else 1.0) * (1.3 if foot != p.meta.preferred_foot else 1.0)
        target = target + self.np_rng.normal(0, noise, 2)
        target = np.clip(target, [1, 1], [L - 1, W - 1])
        start = self.ball_pos.copy()
        if aerial:
            angle = self.rng.uniform(22, 35)
            vel = physics.aerial_launch_velocity(start, target, angle)
            self.ball_spin = np.array([0.0, 0.0, self.rng.uniform(-12, 12)])
            start[2] = 0.03
        else:
            vel = physics.ground_pass_velocity(start, target, arrival_speed=self.rng.uniform(5.0, 9.0))
            self.ball_spin = None
        ev = self._emit(
            "pass",
            p,
            end_x=round(float(target[0]), 2),
            end_y=round(float(target[1]), 2),
            kind="aerial" if aerial else "ground",
            intended_receiver_id=receiver.id,
            speed_kmh=round(float(np.linalg.norm(vel)) * 3.6, 1),
            distance=round(d, 1),
            pressure_distance=round(pressure_d, 2),
            body_part=f"{foot}_foot",
            weak_foot=foot != p.meta.preferred_foot,
            outcome=None,
        )
        self.pending_pass = ev
        self._kick(p, start, vel, foot)
        self.intended_receiver = receiver

    def _shoot(self, p: SimPlayer, dist_goal: float, header: bool = False) -> None:
        gx = goal_x_for(p.team)
        # Shooters aim for a corner; execution error grows with distance.
        if self.rng.random() < 0.5:
            aim_y = self.rng.uniform(physics.GOAL_Y_MIN + 0.3, physics.GOAL_Y_MIN + 1.6)
        else:
            aim_y = self.rng.uniform(physics.GOAL_Y_MAX - 1.6, physics.GOAL_Y_MAX - 0.3)
        aim_z = self.rng.uniform(0.1, 1.2) if header else self.rng.uniform(0.1, 2.2)  # headers aim down
        _, pressure_d = self._nearest(self._team(other(p.team)), np.array([*p.pos, 0.0]))
        foot = "head" if header else self._choose_foot(p, pressure_d)
        weak = 1.4 if header else 1.25 if foot != p.meta.preferred_foot else 1.0
        aim_y += self.rng.gauss(0, (0.14 * dist_goal + 1.4) * weak)
        aim_z = max(0.0, aim_z + self.rng.gauss(0, 0.07 * dist_goal * weak))
        z0 = float(self.ball_pos[2]) if header else 0.03
        start = np.array([self.ball_pos[0], self.ball_pos[1], z0])
        delta = np.array([gx, aim_y]) - start[:2]
        horiz = float(np.linalg.norm(delta))
        speed = self.rng.uniform(12, 19) if header else self.rng.uniform(19, 31)
        flight = horiz / speed * 1.05
        vz = (aim_z - z0 + 0.5 * physics.G * flight**2) / flight
        vel = np.array([*(delta / horiz * speed), vz])
        half_angle = math.atan2(physics.GOAL_WIDTH / 2, max(dist_goal, 1.0))
        xg = 1 / (1 + math.exp(-(0.2 - 0.12 * dist_goal + 1.2 * 2 * half_angle)))
        if header:
            xg *= 0.6  # headers convert far less often than footed shots from the same spot
        ev = self._emit(
            "shot",
            p,
            end_x=gx,
            end_y=round(aim_y, 2),
            speed_kmh=round(float(np.linalg.norm(vel)) * 3.6, 1),
            distance=round(dist_goal, 1),
            xg=round(xg, 3),
            target_z=round(aim_z, 2),
            body_part="head" if header else f"{foot}_foot",
            weak_foot=not header and foot != p.meta.preferred_foot,
            outcome=None,
            _aim_y=aim_y,
        )
        self.pending_shot = ev
        self._kick(p, start, vel, foot)
        self.ball_spin = None if header else np.array([0.0, 0.0, self.rng.uniform(-8, 8)])

    def _choose_foot(self, p: SimPlayer, pressure_d: float) -> str:
        """Mostly the strong foot; under pressure players are forced onto the weak one more often."""
        weak_prob = 0.32 if pressure_d < 3 else 0.18
        weak = "left" if p.meta.preferred_foot == "right" else "right"
        return weak if self.rng.random() < weak_prob else p.meta.preferred_foot

    def _kick(self, p: SimPlayer, start: np.ndarray, vel: np.ndarray, foot: str) -> None:
        p.kick_foot = foot
        p.kick_point = start[:2].copy()
        p.kick_until = self.t + 0.25
        self.ball_pos = start
        self.ball_vel = vel
        self.kick_origin = start[:2].copy()
        self.owner = None
        self.kicker = p
        self.kick_time = self.t
        self.last_touch = p

    # ------------------------------------------------------------- free ball
    def _free_ball(self) -> None:
        sub_dt = self.dt / self.substeps
        for _ in range(self.substeps):
            self.ball_pos, self.ball_vel = physics.step(self.ball_pos, self.ball_vel, sub_dt, self.ball_spin)
            if self._check_boundaries():
                return
        self._check_control()

    def _check_boundaries(self) -> bool:
        x, y, z = self.ball_pos
        if 0.0 < x < L and 0.0 < y < W:
            return False
        last_team = self.last_touch.team if self.last_touch else self.possession_team
        if x <= 0.0 or x >= L:
            attacking = "home" if x >= L else "away"  # team attacking this goal
            if physics.GOAL_Y_MIN < y < physics.GOAL_Y_MAX and z < physics.GOAL_HEIGHT:
                self._goal(attacking)
                return True
            if self.pending_shot is not None:
                self.pending_shot["data"]["outcome"] = "off_target"
                self.pending_shot = None
            if last_team == attacking:
                gk_spot = to_world(other(attacking), 6.0, 34.0)
                self._restart("goal_kick", other(attacking), gk_spot)
            else:
                corner_y = 0.5 if y < W / 2 else W - 0.5
                self._restart("corner", attacking, np.array([L - 0.5 if x >= L else 0.5, corner_y]))
            return True
        spot = np.array([float(np.clip(x, 1.0, L - 1.0)), 0.3 if y <= 0 else W - 0.3])
        self._restart("throw_in", other(last_team), spot, pause=1.2)
        return True

    def _goal(self, scoring_team: str) -> None:
        scorer = self.last_touch if self.last_touch and self.last_touch.team == scoring_team else None
        if self.pending_shot is not None:
            self.pending_shot["data"]["outcome"] = "goal"
            self.pending_shot = None
        self._resolve_pending("goal")
        self.score[scoring_team] += 1
        self._emit(
            "goal",
            scorer,
            team=scoring_team,
            own_goal=scorer is None,
            score=dict(self.score),
        )
        self._kickoff(other(scoring_team))
        self.dead_until = self.t + 4.0  # celebration
        self.hold_until = self.dead_until + 0.3

    def _check_control(self) -> None:
        if self.t < self.dead_until:
            return
        best: tuple[float, SimPlayer] | None = None
        travelled = float(np.linalg.norm(self.ball_pos[:2] - self.kick_origin))
        for p in self.players:
            if p is self.kicker and self.t - self.kick_time < 0.3:
                continue
            gk = p.meta.role == "GK"
            if p is not self.intended_receiver and not gk:
                # Cutting out a moving ball is harder than receiving one you were aiming for.
                if travelled < 3.0 or self.rng.random() > 0.3:
                    continue
            if gk and self.pending_shot is not None:
                speed = float(np.linalg.norm(self.ball_vel))
                if self.rng.random() > float(np.clip(1.5 - speed / 30.0, 0.35, 0.9)):
                    continue
            reach, max_z = (1.6, 2.6) if gk else (1.0, HEADER_MAX_Z)
            if self.ball_pos[2] > max_z:
                continue
            d = float(np.linalg.norm(p.pos - self.ball_pos[:2]))
            if d < reach and (best is None or d < best[0]):
                best = (d, p)
        if best is None:
            return
        p = best[1]
        z = float(self.ball_pos[2])
        if p.meta.role != "GK" and z > HEADER_MIN_Z:
            descending = self.ball_vel[2] < 0
            if not descending or (z <= 1.9 and self.rng.random() < 0.5):
                if z > 1.9:
                    return  # rising ball above chest height: let it go over
            else:
                self._header(p)
                return
        if self.pending_shot is not None:
            shooter_team = self.pending_shot["team"]
            if p.team != shooter_team:
                self.pending_shot["data"]["outcome"] = "saved" if p.meta.role == "GK" else "blocked"
            else:
                self.pending_shot["data"]["outcome"] = "rebound_teammate"
            self.pending_shot = None
            self._set_owner(p, "save" if p.meta.role == "GK" else "block")
            return
        if self.pending_pass is not None:
            passer_team = self.pending_pass["team"]
            if p.team == passer_team and p.id != self.pending_pass["player_id"]:
                self._resolve_pending("complete", p)
            elif p.team != passer_team:
                self._resolve_pending("intercepted", p)
            else:
                self._resolve_pending("incomplete", p)
            self._set_owner(p, "interception")
            return
        self._set_owner(p, "loose_ball")

    def _header(self, p: SimPlayer) -> None:
        """Ball met at head height: redirect it without taking control."""
        from_cross = (
            self.pending_pass is not None
            and self.pending_pass["data"].get("kind") == "cross"
            and self.pending_pass["team"] == p.team
        )
        if self.pending_shot is not None:
            same = self.pending_shot["team"] == p.team
            self.pending_shot["data"]["outcome"] = "rebound_teammate" if same else "blocked"
            self.pending_shot = None
        if self.pending_pass is not None:
            passer_team = self.pending_pass["team"]
            if p.team == passer_team and p.id != self.pending_pass["player_id"]:
                self._resolve_pending("complete", p)
            elif p.team != passer_team:
                self._resolve_pending("intercepted", p)
            else:
                self._resolve_pending("incomplete", p)
        if p.team != self.possession_team:
            self._emit("possession_change", p, cause="header", from_team=self.possession_team)
            self.possession_team = p.team

        goal = np.array([goal_x_for(p.team), W / 2])
        dist_goal = float(np.linalg.norm(goal - p.pos))
        if (dist_goal < 14 or (from_cross and dist_goal < 24)) and abs(p.pos[1] - W / 2) < 18:
            self._shoot(p, dist_goal, header=True)
            return
        mates = [m for m in self._team(p.team) if m is not p and m.meta.role != "GK" and 4 < np.linalg.norm(m.pos - p.pos) < 18]
        if mates:
            # Headed lay-off: flat so it arrives at a teammate's feet, not their head.
            receiver = max(mates, key=lambda m: to_attacking(p.team, *m.pos)[0] + self.rng.gauss(0, 4))
            target = receiver.pos + self.np_rng.normal(0, 1.5, 2)
            self.intended_receiver = receiver
            angle = self.rng.uniform(8, 18)
        else:  # clearance: head it long and high, away from own goal
            ahead = np.array([1.0 if p.team == "home" else -1.0, self.rng.uniform(-0.5, 0.5)])
            target = p.pos + ahead / np.linalg.norm(ahead) * self.rng.uniform(15, 25)
            receiver = None
            self.intended_receiver = None
            angle = self.rng.uniform(30, 45)
        target = np.clip(target, [1, 1], [L - 1, W - 1])
        start = self.ball_pos.copy()
        d = float(np.linalg.norm(target - start[:2]))
        vel = physics.aerial_launch_velocity(np.array([start[0], start[1], 0.0]), target, angle)
        vel *= 0.92  # launched from head height, so it carries a little further than from the ground
        ev = self._emit(
            "pass",
            p,
            end_x=round(float(target[0]), 2),
            end_y=round(float(target[1]), 2),
            kind="header" if receiver else "clearance",
            intended_receiver_id=receiver.id if receiver else None,
            speed_kmh=round(float(np.linalg.norm(vel)) * 3.6, 1),
            distance=round(d, 1),
            pressure_distance=round(self._nearest(self._team(other(p.team)), np.array([*p.pos, 0.0]))[1], 2),
            body_part="head",
            weak_foot=False,
            height_m=round(float(start[2]), 2),
            outcome=None,
        )
        self.pending_pass = ev
        self.ball_spin = None
        self._kick(p, start, vel, "head")

    # ------------------------------------------------------------- main loop
    def _feet(self, p: SimPlayer) -> tuple[str, float, float, float, float, float, float]:
        """Gait model: feet alternate along the heading; stride length and cadence grow with speed."""
        speed = float(np.linalg.norm(p.vel))
        if speed > 0.3:
            p.heading = p.vel / speed
        fwd = p.heading
        left_side = np.array([-fwd[1], fwd[0]])
        cycle_hz = 0.8 + 0.12 * speed  # one cycle = two steps (~1.8 to 3.5 steps/s)
        p.gait_phase = (p.gait_phase + 2 * math.pi * cycle_hz * self.dt) % (2 * math.pi)
        reach = min(0.55, 0.06 * speed + 0.03)
        lift = 0.2 * min(1.0, speed / 3.0)
        out: list[float] = []
        for side, phase, sign in (("left", p.gait_phase, 1.0), ("right", p.gait_phase + math.pi, -1.0)):
            if p.kick_foot == side and self.t < p.kick_until and p.kick_point is not None:
                xy, z = p.kick_point, 0.12  # striking foot on the ball
            else:
                xy = p.pos + left_side * 0.12 * sign + fwd * reach * math.sin(phase)
                z = lift * max(0.0, math.cos(phase))  # swing foot lifts while moving forward
            out += [round(float(xy[0]), 2), round(float(xy[1]), 2), round(float(z), 2)]
        return (p.id, *out)  # type: ignore[return-value]

    def _record(self) -> None:
        self.frames.append(
            Frame(
                f=self.frame_idx,
                t=round(self.t, 2),
                ball=tuple(round(float(v), 2) for v in self.ball_pos),
                players=[(p.id, round(float(p.pos[0]), 2), round(float(p.pos[1]), 2)) for p in self.players],
                feet=[self._feet(p) for p in self.players],
                owner=self.owner.id if self.owner else None,
                score=dict(self.score),
            )
        )

    def run(self) -> Match:
        total = self.minutes * 60.0
        half = total / 2
        self._kickoff("home")
        second_half_started = False
        while self.t < total:
            if not second_half_started and self.t >= half:
                second_half_started = True
                self._resolve_pending("out")
                self.pending_shot = None
                self._emit("half_time", score=dict(self.score))
                self._kickoff("away")
            self._update_players()
            if self.owner is not None:
                if self.t >= self.dead_until:
                    if not self._check_pressure_and_tackle(self.owner):
                        if self.t >= self.hold_until:
                            self._decide(self.owner)
                        else:
                            self._dribble(self.owner)
            else:
                self._free_ball()
            self._record()
            self.t += self.dt
            self.frame_idx += 1
        self._resolve_pending("out")
        self._emit("full_time", score=dict(self.score))
        for ev in self.events:
            ev["data"].pop("_aim_y", None)
        meta = MatchMeta(
            match_id=self.match_id,
            seed=self.seed,
            minutes=self.minutes,
            fps=self.fps,
            teams=self.teams,
            players=[p.meta for p in self.players],
            final_score=dict(self.score),
        )
        return Match(meta=meta, frames=self.frames, events=[Event(**e) for e in self.events])


def generate_match(seed: int = 7, minutes: int = 20, fps: int = 10, match_id: str | None = None) -> Match:
    return MatchSimulator(seed=seed, minutes=minutes, fps=fps, match_id=match_id).run()
