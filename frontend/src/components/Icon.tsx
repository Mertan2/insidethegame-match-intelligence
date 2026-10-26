/** Inline SVG icons (stroke, currentColor), so the UI never depends on emoji glyphs. */
const PATHS: Record<string, React.ReactNode> = {
  play: <path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none" />,
  pause: <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" stroke="none" />,
  next: <path d="M5 5v14l10-7zM17 5h2v14h-2z" fill="currentColor" stroke="none" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  voice: <path d="M4 10v4h4l5 4V6L8 10zM16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" />,
  voiceOff: <path d="M4 10v4h4l5 4V6L8 10zM16 9l5 6M21 9l-5 6" />,
  studio: <path d="M3 5h18v12H3zM8 21h8M12 17v4" />,
  settings: <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM4 12h2M18 12h2M12 4v2M12 18v2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M6.3 17.7l1.4-1.4M16.3 7.7l1.4-1.4" />,
  film: <path d="M3 5h18v14H3zM7 5v14M17 5v14M3 10h4M3 14h4M17 10h4M17 14h4" />,
  bolt: <path d="M13 2L5 13h6l-1 9 9-12h-6z" fill="currentColor" stroke="none" />,
  stadium: <path d="M3 9c0-2.2 4-4 9-4s9 1.8 9 4-4 4-9 4-9-1.8-9-4zM3 9v6c0 2.2 4 4 9 4s9-1.8 9-4V9M9 13v5M15 13v5" />,
  mic: <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6" />,
  chart: <path d="M4 20h16M7 16v-5M12 16V7M17 16v-3" />,
  tool: <path d="M14.5 4.5a4 4 0 0 0-5 5L4 15v5h5l5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2.5-2.5z" />,
  goal: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7l4.5 3.3-1.7 5.4H9.2L7.5 10.3zM12 3v4M20.6 9.3l-4.1 1M16.6 20.3l-1.8-4.6M7.4 20.3l1.8-4.6M3.4 9.3l4.1 1" />
    </>
  ),
  save: <path d="M7 11V6a2 2 0 1 1 4 0v4M11 9V5a2 2 0 1 1 4 0v5M15 10V7a2 2 0 1 1 4 0v7a6 6 0 0 1-6 6h-2a6 6 0 0 1-6-6v-2a2 2 0 1 1 4 0" />,
  shot: <path d="M6 18L18 6M9 6h9v9" />,
  kick: <path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none" />,
};

export function Icon({ name, size = 16, className = "" }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg
      className={`ico ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name] ?? null}
    </svg>
  );
}

/** The mark used for the brand: a small diamond. */
export function BrandMark({ size = 14 }: { size?: number }) {
  return (
    <svg className="ico brand-ico" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 2l10 10-10 10L2 12z" fill="currentColor" />
    </svg>
  );
}
