"""Ball physics shared by the synthetic generator and the forecast plugin.

Coordinates: x along pitch length (0..105 m), y across (0..68 m), z height (m).
"""

from __future__ import annotations

import math

import numpy as np

G = 9.81
# 0.5 * air density * drag coefficient * cross-section / mass  (per metre)
DRAG_K = 0.5 * 1.2 * 0.25 * 0.038 / 0.43
# Magnus lift coefficient applied to spin x velocity (spin in rad/s)
MAGNUS_K = 0.0024
ROLL_DECEL = 1.4  # m/s^2, rolling friction on grass
BOUNCE_RESTITUTION = 0.5
BOUNCE_FRICTION = 0.8

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
GOAL_WIDTH = 7.32
GOAL_HEIGHT = 2.44
GOAL_Y_MIN = PITCH_WIDTH / 2 - GOAL_WIDTH / 2
GOAL_Y_MAX = PITCH_WIDTH / 2 + GOAL_WIDTH / 2


def is_airborne(pos: np.ndarray, vel: np.ndarray) -> bool:
    return pos[2] > 0.02 or vel[2] > 0.05


def step(pos: np.ndarray, vel: np.ndarray, dt: float, spin: np.ndarray | None = None):
    """Advance ball state by dt. Returns (pos, vel) as new arrays.

    Scalar math on purpose: numpy call overhead dominates for 3-element vectors,
    and this runs hundreds of thousands of times per generated match.
    """
    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    vx, vy, vz = float(vel[0]), float(vel[1]), float(vel[2])
    if pz > 0.02 or vz > 0.05:  # airborne
        k = DRAG_K * math.sqrt(vx * vx + vy * vy + vz * vz)
        ax, ay, az = -k * vx, -k * vy, -G - k * vz
        if spin is not None:
            sx, sy, sz = float(spin[0]), float(spin[1]), float(spin[2])
            ax += MAGNUS_K * (sy * vz - sz * vy)
            ay += MAGNUS_K * (sz * vx - sx * vz)
            az += MAGNUS_K * (sx * vy - sy * vx)
        vx, vy, vz = vx + ax * dt, vy + ay * dt, vz + az * dt
        px, py, pz = px + vx * dt, py + vy * dt, pz + vz * dt
        if pz <= 0.0:
            pz = 0.0
            if vz < -1.0:
                vz = -vz * BOUNCE_RESTITUTION
                vx *= BOUNCE_FRICTION
                vy *= BOUNCE_FRICTION
            else:
                vz = 0.0
    else:
        pz = vz = 0.0
        hs = math.sqrt(vx * vx + vy * vy)
        if hs > 0.0:
            ratio = max(0.0, hs - ROLL_DECEL * dt) / hs
            vx, vy = vx * ratio, vy * ratio
        px, py = px + vx * dt, py + vy * dt
    return np.array([px, py, pz]), np.array([vx, vy, vz])


def simulate(
    pos: np.ndarray,
    vel: np.ndarray,
    duration: float = 4.0,
    dt: float = 0.02,
    sample_every: float = 0.1,
    spin: np.ndarray | None = None,
) -> list[tuple[float, np.ndarray]]:
    """Integrate forward and return sampled (t, pos) points, stopping when the ball rests."""
    out: list[tuple[float, np.ndarray]] = [(0.0, pos.astype(float).copy())]
    p, v = pos.astype(float), vel.astype(float)
    t = 0.0
    next_sample = sample_every
    while t < duration:
        p, v = step(p, v, dt, spin)
        t += dt
        if t + 1e-9 >= next_sample:
            out.append((round(t, 3), p))  # step() returns fresh arrays, no copy needed
            next_sample += sample_every
        if not is_airborne(p, v) and math.hypot(v[0], v[1]) < 0.05:
            break
    return out


def first_landing(pos: np.ndarray, vel: np.ndarray, dt: float = 0.01, max_t: float = 8.0):
    """Time and position of first ground contact for an airborne ball, else None."""
    if not is_airborne(pos, vel):
        return None
    p, v = pos.astype(float), vel.astype(float)
    t = 0.0
    while t < max_t:
        p_new, v_new = step(p, v, dt)
        t += dt
        if p_new[2] <= 0.0 and v[2] < 0.0:
            return t, p_new
        p, v = p_new, v_new
    return None


def aerial_launch_velocity(start: np.ndarray, target_xy: np.ndarray, angle_deg: float) -> np.ndarray:
    """Velocity that makes a lofted ball first land at target_xy, corrected for drag."""
    d_vec = np.asarray(target_xy, dtype=float) - start[:2]
    dist = float(np.linalg.norm(d_vec))
    if dist < 1e-6:
        return np.zeros(3)
    direction = d_vec / dist
    theta = math.radians(angle_deg)
    v0 = math.sqrt(dist * G / math.sin(2 * theta))
    for _ in range(8):
        vel = np.array([*(direction * v0 * math.cos(theta)), v0 * math.sin(theta)])
        landing = first_landing(np.array([start[0], start[1], 0.03]), vel)
        if landing is None:
            break
        rng = float(np.linalg.norm(landing[1][:2] - start[:2]))
        if rng < 1e-6:
            break
        v0 *= math.sqrt(dist / rng)
    return np.array([*(direction * v0 * math.cos(theta)), v0 * math.sin(theta)])


def ground_pass_velocity(start: np.ndarray, target_xy: np.ndarray, arrival_speed: float = 3.0) -> np.ndarray:
    d_vec = np.asarray(target_xy, dtype=float) - start[:2]
    dist = float(np.linalg.norm(d_vec))
    if dist < 1e-6:
        return np.zeros(3)
    v0 = math.sqrt(arrival_speed**2 + 2 * ROLL_DECEL * dist)
    return np.array([*(d_vec / dist * v0), 0.0])


def goal_line_crossing(points: list[tuple[float, np.ndarray]], goal_x: float):
    """Interpolated (t, y, z) where a sampled trajectory crosses x = goal_x, else None."""
    for (t0, p0), (t1, p1) in zip(points, points[1:]):
        if (p0[0] - goal_x) * (p1[0] - goal_x) <= 0 and p0[0] != p1[0]:
            f = (goal_x - p0[0]) / (p1[0] - p0[0])
            return t0 + f * (t1 - t0), p0[1] + f * (p1[1] - p0[1]), p0[2] + f * (p1[2] - p0[2])
    return None
