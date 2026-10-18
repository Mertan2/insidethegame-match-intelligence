import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import { useMemo, useRef } from "react";
import { Vector3 } from "three";
import type { ForecastPayload, Frame, MatchMeta } from "../types";

const L = 105;
const W = 68;

/** Pitch metres (x along length, y across, z up) -> three.js world (y up). */
const toWorld = (x: number, y: number, z = 0): [number, number, number] => [x - L / 2, z, y - W / 2];

interface Props {
  meta: MatchMeta;
  frame: Frame | null;
  forecast?: ForecastPayload;
  focusId: string | null;
}

export function Ball3D({ meta, frame, forecast, focusId }: Props) {
  const colors = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of meta.players) m.set(p.id, p.role === "GK" ? "#f2d14b" : meta.teams[p.team].color);
    return m;
  }, [meta]);

  const feet = useMemo(() => new Map((frame?.feet ?? []).map((f) => [f[0], f])), [frame]);

  const trajectory = forecast?.active && forecast.trajectory && forecast.trajectory.length > 1
    ? forecast.trajectory.map(([x, y, z]) => toWorld(x, y, z))
    : null;

  return (
    <Canvas camera={{ position: [0, 62, 78], fov: 45 }} shadows dpr={[1, 2]}>
      <color attach="background" args={["#0c1420"]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[30, 60, 20]} intensity={1.1} castShadow />
      <PitchMesh />
      {frame?.players.map(([id, x, y]) => (
        <Footballer key={id} x={x} y={y} feet={feet.get(id)} color={colors.get(id) ?? "#888"} />
      ))}
      {frame && (
        <mesh position={toWorld(frame.ball[0], frame.ball[1], frame.ball[2] + 0.33)} castShadow>
          <sphereGeometry args={[0.33, 20, 20]} />
          <meshStandardMaterial color="#ffffff" emissive="#444" />
        </mesh>
      )}
      {trajectory && <Line points={trajectory} color="#ffe65a" lineWidth={2.5} dashed dashSize={0.8} gapSize={0.5} />}
      {forecast?.active && forecast.landing && (
        <mesh position={toWorld(forecast.landing.x, forecast.landing.y, 0.03)} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.6, 1.0, 32]} />
          <meshBasicMaterial color="#ffe65a" />
        </mesh>
      )}
      {forecast?.active && forecast.goal_crossing && (
        <mesh
          position={toWorld(forecast.goal_crossing.goal === "away" ? L : 0, forecast.goal_crossing.y, forecast.goal_crossing.z)}
        >
          <sphereGeometry args={[0.35, 12, 12]} />
          <meshBasicMaterial color={forecast.goal_crossing.on_target ? "#ff4f4f" : "#8899aa"} transparent opacity={0.8} />
        </mesh>
      )}
      <OrbitControls makeDefault target={[0, 0, 0]} maxPolarAngle={Math.PI / 2.1} />
      <FollowCamera frame={frame} focusId={focusId} />
    </Canvas>
  );
}

const HIP_Z = 0.95;
type Feet = [string, number, number, number, number, number, number];

/** Torso on top of two legs drawn from the hip to the tracked foot positions. */
function Footballer({ x, y, feet, color }: { x: number; y: number; feet?: Feet; color: string }) {
  const hip = toWorld(x, y, HIP_Z);
  return (
    <group>
      <mesh position={toWorld(x, y, HIP_Z + 0.45)} castShadow>
        <cylinderGeometry args={[0.32, 0.26, 0.9, 10]} />
        <meshStandardMaterial color={color} />
      </mesh>
      <mesh position={toWorld(x, y, HIP_Z + 1.05)} castShadow>
        <sphereGeometry args={[0.16, 10, 10]} />
        <meshStandardMaterial color="#e8c9a8" />
      </mesh>
      {feet ? (
        <>
          <Line points={[hip, toWorld(feet[1], feet[2], feet[3])]} color="#f4f4f4" lineWidth={3} />
          <Line points={[hip, toWorld(feet[4], feet[5], feet[6])]} color="#cfcfcf" lineWidth={3} />
        </>
      ) : (
        <mesh position={toWorld(x, y, HIP_Z / 2)}>
          <cylinderGeometry args={[0.18, 0.18, HIP_Z, 8]} />
          <meshStandardMaterial color="#ddd" />
        </mesh>
      )}
    </group>
  );
}

const HOME_TARGET = new Vector3(0, 0, 0);
const HOME_OFFSET = new Vector3(0, 62, 78);
const FOLLOW_OFFSET = new Vector3(0, 18, 24);

/** Player-focus camera: glides after the focused player; glides home when focus is cleared. */
function FollowCamera({ frame, focusId }: { frame: Frame | null; focusId: string | null }) {
  const controls = useThree((s) => s.controls) as unknown as { target: Vector3; update: () => void } | null;
  const desiredTarget = useRef(new Vector3());
  const desiredCamera = useRef(new Vector3());

  useFrame(({ camera }, delta) => {
    if (!controls) return;
    const player = focusId ? frame?.players.find(([id]) => id === focusId) : undefined;
    if (player) {
      desiredTarget.current.set(...toWorld(player[1], player[2], 0));
      desiredCamera.current.copy(desiredTarget.current).add(FOLLOW_OFFSET);
    } else if (controls.target.distanceTo(HOME_TARGET) > 0.5) {
      desiredTarget.current.copy(HOME_TARGET);
      desiredCamera.current.copy(HOME_TARGET).add(HOME_OFFSET);
    } else {
      return; // free orbit
    }
    const k = 1 - Math.exp(-delta * 3);
    controls.target.lerp(desiredTarget.current, k);
    camera.position.lerp(desiredCamera.current, k);
    controls.update();
  });
  return null;
}

function PitchMesh() {
  const lines = useMemo(() => {
    const segs: [number, number, number][][] = [];
    const rect = (x0: number, y0: number, x1: number, y1: number) =>
      segs.push([toWorld(x0, y0, 0.02), toWorld(x1, y0, 0.02), toWorld(x1, y1, 0.02), toWorld(x0, y1, 0.02), toWorld(x0, y0, 0.02)]);
    rect(0, 0, L, W);
    rect(0, W / 2 - 20.16, 16.5, W / 2 + 20.16);
    rect(L - 16.5, W / 2 - 20.16, L, W / 2 + 20.16);
    rect(0, W / 2 - 9.16, 5.5, W / 2 + 9.16);
    rect(L - 5.5, W / 2 - 9.16, L, W / 2 + 9.16);
    segs.push([toWorld(L / 2, 0, 0.02), toWorld(L / 2, W, 0.02)]);
    const circle: [number, number, number][] = [];
    for (let i = 0; i <= 64; i++) {
      const a = (i / 64) * Math.PI * 2;
      circle.push(toWorld(L / 2 + 9.15 * Math.cos(a), W / 2 + 9.15 * Math.sin(a), 0.02));
    }
    segs.push(circle);
    return segs;
  }, []);

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[L + 8, W + 8]} />
        <meshStandardMaterial color="#1f6b3a" />
      </mesh>
      {lines.map((pts, i) => (
        <Line key={i} points={pts} color="white" lineWidth={1.5} />
      ))}
      {[0, L].map((gx) => (
        <group key={gx}>
          {[W / 2 - 3.66, W / 2 + 3.66].map((gy) => (
            <mesh key={gy} position={toWorld(gx, gy, 1.22)}>
              <cylinderGeometry args={[0.06, 0.06, 2.44, 8]} />
              <meshStandardMaterial color="white" />
            </mesh>
          ))}
          <mesh position={toWorld(gx, W / 2, 2.44)} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.06, 0.06, 7.32, 8]} />
            <meshStandardMaterial color="white" />
          </mesh>
        </group>
      ))}
    </group>
  );
}
