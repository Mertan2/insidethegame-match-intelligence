import numpy as np

from app import physics


def test_aerial_launch_lands_on_target():
    start = np.array([30.0, 20.0, 0.0])
    target = np.array([65.0, 40.0])
    vel = physics.aerial_launch_velocity(start, target, 30)
    t, landing = physics.first_landing(np.array([30.0, 20.0, 0.03]), vel)
    assert np.linalg.norm(landing[:2] - target) < 0.5
    assert 1.0 < t < 4.0


def test_ground_pass_arrives_with_requested_speed():
    start = np.array([10.0, 10.0, 0.0])
    target = np.array([30.0, 10.0])
    vel = physics.ground_pass_velocity(start, target, arrival_speed=4.0)
    p, v = start.copy(), vel.copy()
    while p[0] < target[0]:
        p, v = physics.step(p, v, 0.01)
    assert abs(np.linalg.norm(v[:2]) - 4.0) < 0.2


def test_goal_line_crossing_interpolates():
    pts = [(0.0, np.array([100.0, 34.0, 1.0])), (0.1, np.array([106.0, 35.0, 1.2]))]
    t, y, z = physics.goal_line_crossing(pts, 105.0)
    assert abs(t - 0.0833) < 1e-3
    assert abs(y - 34.833) < 1e-2
