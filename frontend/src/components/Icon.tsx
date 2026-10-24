/** The few drawn icons the UI needs: one 1.75px stroke, square caps, 24px grid. */
const PATHS = {
  close: <path d="M6 6l12 12M18 6L6 18" />,
  back: <path d="M15 5l-7 7 7 7" />,
  send: <path d="M5 12h13M13 6l6 6-6 6" />,
  mic: (
    <>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
    </>
  ),
  play: <path d="M8 5.5v13l10-6.5z" fill="currentColor" stroke="none" />,
  pause: <path d="M8 5v14M16 5v14" strokeWidth="2.5" />,
  stop: <rect x="7" y="7" width="10" height="10" fill="currentColor" stroke="none" />,
  // a pause bar beside a spotlight: "stop the film here and step in"
  pauseTalk: (
    <>
      <path d="M5 5v14M9.5 5v14" />
      <circle cx="17" cy="12" r="4" />
    </>
  ),
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden
    >
      {PATHS[name]}
    </svg>
  );
}
