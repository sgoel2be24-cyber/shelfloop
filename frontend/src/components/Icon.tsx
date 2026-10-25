/**
 * Hand-tuned stroke icon set (feather-style 24×24, currentColor).
 * Replaces emoji-as-UI-icon so the product reads as designed, not templated.
 */
const PATHS: Record<string, React.ReactNode> = {
  home: (
    <>
      <path d="M3 9.5 12 3l9 6.5V20a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 20z" />
      <path d="M9 21.5v-7h6v7" />
    </>
  ),
  ledger: (
    <>
      <rect x="5" y="3.5" width="14" height="17" rx="1.5" />
      <path d="M9 3.5v17M12.5 8h4M12.5 12h4" />
    </>
  ),
  graph: (
    <>
      <circle cx="18" cy="5" r="2.6" />
      <circle cx="6" cy="12" r="2.6" />
      <circle cx="18" cy="19" r="2.6" />
      <path d="m8.4 10.8 7.2-4.4M8.4 13.2l7.2 4.4" />
    </>
  ),
  bolt: <path d="M13 2.5 4.5 14H11l-1 7.5L18.5 10H12z" />,
  file: (
    <>
      <path d="M13.5 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5V8z" />
      <path d="M13.5 3v5h5M9 13h6M9 17h6" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="16" rx="1.5" />
      <path d="M8 2.5V7M16 2.5V7M3.5 10.5h17" />
    </>
  ),
  box: (
    <>
      <path d="M21 8.5v9a1.5 1.5 0 0 1-.8 1.3l-7.5 3.8a1.5 1.5 0 0 1-1.4 0L3.8 18.8A1.5 1.5 0 0 1 3 17.5v-9" />
      <path d="M3.3 7.8 12 3l8.7 4.8L12 12.4z" />
      <path d="M12 12.4V21" />
    </>
  ),
  pencil: (
    <>
      <path d="M12.5 20.5H21" />
      <path d="m16.7 3.6a2.1 2.1 0 0 1 3 3L7.5 18.8 3.5 20l1.2-4z" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.3 2.7 2.7L16.2 9" />
    </>
  ),
  mic: (
    <>
      <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
      <path d="M19 10.5v.5a7 7 0 0 1-14 0v-.5M12 18.5V22M8.5 22h7" />
    </>
  ),
  speaker: (
    <>
      <path d="M11 5.5 6.5 9H3v6h3.5L11 18.5z" />
      <path d="M15.2 9a4.2 4.2 0 0 1 0 6M18 6.6a8 8 0 0 1 0 10.8" />
    </>
  ),
  refresh: (
    <>
      <path d="M21 3.5v6h-6M3 20.5v-6h6" />
      <path d="M4.5 10a8 8 0 0 1 13.2-3L21 9.5M3 14.5l3.3 2.5a8 8 0 0 0 13.2-3" />
    </>
  ),
  x: <path d="M6 6l12 12M18 6 6 18" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20.5 20.5-4.6-4.6" />
    </>
  ),
  logout: (
    <>
      <path d="M9.5 21H5.5A1.5 1.5 0 0 1 4 19.5v-15A1.5 1.5 0 0 1 5.5 3h4" />
      <path d="m16 16.5 4.5-4.5L16 7.5M20.5 12H9.5" />
    </>
  ),
  type: (
    <>
      <path d="M4 6.5V4h16v2.5M12 4v16M9 20h6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 6.5V12l3.5 2" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
}

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 20,
  strokeWidth = 1.9,
  className = '',
}: {
  name: IconName | string
  size?: number
  strokeWidth?: number
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {PATHS[name] ?? PATHS.box}
    </svg>
  )
}
