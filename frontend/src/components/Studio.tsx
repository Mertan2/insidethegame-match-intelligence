import { useEffect } from "react";
import { Broadcast, type BroadcastProps } from "./Broadcast";
import { BrandMark, Icon } from "./Icon";

interface Props extends BroadcastProps {
  speed: number;
  speaking: boolean;
  voiceOn: boolean;
  voiceAvailable: boolean;
  onControl: (msg: { action?: string; speed?: number }) => void;
  onVoice: () => void;
  onHighlights: () => void;
  onExit: () => void;
}

/** Studio mode: the broadcast output full screen, with only the transport on top. Esc returns. */
export function Studio(props: Props) {
  const { paused, ended, speed, speaking, voiceOn, voiceAvailable, busy, moments, frame } = props;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onExit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="studio" role="region" aria-label="Studio output">
      <div className="studio-bar">
        <span className="studio-brand">
          <BrandMark size={12} /> INSIDE THE GAME · STUDIO
        </span>
        <span className="studio-bar-gap" />
        <button onClick={() => props.onControl({ action: paused ? "play" : "pause" })} disabled={ended}>
          {paused ? <><Icon name="play" /> Play</> : <><Icon name="pause" /> Pause</>}
        </button>
        <select value={speed} onChange={(e) => props.onControl({ speed: Number(e.target.value) })} aria-label="Speed">
          {[1, 2, 4, 8, 16, 32].map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
        {voiceAvailable && (
          <button className={`voice-toggle ${voiceOn ? "on" : ""}`} onClick={props.onVoice}>
            <Icon name={voiceOn ? "voice" : "voiceOff"} /> {voiceOn ? (speaking ? "Speaking…" : "Voice on") : "Voice off"}
          </button>
        )}
        <button className="highlights-btn" onClick={props.onHighlights} disabled={busy !== null || moments.filter((m) => m.t <= (frame?.t ?? 0)).length === 0}>
          <Icon name="film" /> {ended ? "Match highlights" : "Highlights so far"}
        </button>
        <button className="studio-exit" onClick={props.onExit} title="Back to the app (Esc)">
          <Icon name="close" /> Exit studio
        </button>
      </div>
      <Broadcast {...props} />
    </div>
  );
}
