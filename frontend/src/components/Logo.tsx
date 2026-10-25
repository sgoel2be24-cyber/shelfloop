/** ShelfLoop mark: a hand-drawn wire basket with a loop of stock — slightly
 * wobbly strokes on purpose, drawn as plain SVG so it needs no asset files. */
export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} fill="none" aria-hidden>
      {/* basket body — intentionally imperfect curves */}
      <path
        d="M9 20c.4-.8 1.2-1.3 2.1-1.2l26 .5c.9 0 1.7.6 2 1.4l.4 1.1c.2.6.1 1.2-.3 1.7l-3 3.9c-1.8 2.3-2.4 3.5-2.9 6.4l-.8 4.6c-.2 1-1 1.7-2 1.7l-13.2-.4c-1 0-1.8-.7-2-1.7l-1.2-6c-.4-2.2-1.1-3.5-2.6-5.3l-3-3.5c-.5-.5-.6-1.3-.3-2z"
        stroke="#2E3192"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      {/* weave lines */}
      <path d="M12.5 24.5c6.5 1.6 17.5 1.5 23.6-.6M15 30.5c5.4 1.3 13.6 1.2 18.9-.5" stroke="#2E3192" strokeWidth="1.6" strokeLinecap="round" opacity=".55" />
      {/* the loop: stock circulating back into the basket */}
      <path
        d="M14 17.5c-2.5-3.4-1.6-7.6 1.5-9.6 3.4-2.2 8.4-1 12.6 1.5 5 3 10.4 3.6 13.4.9"
        stroke="#E8702A"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path d="m38.6 14.2 3.2-3.8.6 5.4" stroke="#E8702A" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="10.5" cy="10.5" r="1.7" fill="#E8702A" />
    </svg>
  )
}

/** Warm little shopfront scene for the login screen. */
export function ShopScene({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 220 120" className={className} fill="none" aria-hidden>
      {/* ground */}
      <path d="M8 104c60 3 150 3 204-1" stroke="#2E3192" strokeWidth="2" strokeLinecap="round" opacity=".35" />
      {/* shop */}
      <rect x="42" y="46" width="96" height="56" rx="2" stroke="#2E3192" strokeWidth="2.4" fill="#fff" />
      <path d="M36 46c1-9 7-16 15-17h78c8 1 14 8 15 17z" stroke="#2E3192" strokeWidth="2.4" fill="#FDF0E4" />
      <path d="M50 62h80M50 78h80" stroke="#2E3192" strokeWidth="1.4" opacity=".35" />
      {/* awning stripes */}
      <path d="M48 36v10M66 34v12M84 33v13M102 33v13M120 34v12M138 36v10" stroke="#E8702A" strokeWidth="3" strokeLinecap="round" opacity=".75" />
      {/* door */}
      <rect x="112" y="66" width="20" height="36" rx="1.5" stroke="#2E3192" strokeWidth="2" fill="#FAF5EC" />
      {/* shelves with tins */}
      <path d="M52 72h26M52 88h26" stroke="#2E3192" strokeWidth="1.6" />
      <rect x="55" y="63" width="6" height="9" rx="1" stroke="#E8702A" strokeWidth="1.6" />
      <rect x="64" y="61" width="6" height="11" rx="1" stroke="#2E3192" strokeWidth="1.6" />
      <rect x="57" y="79" width="7" height="9" rx="1" stroke="#2E3192" strokeWidth="1.6" />
      <rect x="68" y="77" width="6" height="11" rx="1" stroke="#E8702A" strokeWidth="1.6" />
      {/* owner stick figure waving */}
      <circle cx="176" cy="56" r="7" stroke="#2E3192" strokeWidth="2.2" />
      <path d="M176 63v22M176 70c-4-2-7-5-8-9M176 68c3-2 5-5 5-9" stroke="#2E3192" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M168 86h16" stroke="#2E3192" strokeWidth="2.2" strokeLinecap="round" />
      {/* crate being passed between them */}
      <rect x="138" y="86" width="16" height="12" rx="1.5" stroke="#E8702A" strokeWidth="2" />
      <path d="M141 86v12M151 86v12" stroke="#E8702A" strokeWidth="1.3" opacity=".6" />
      {/* floating loop arrow above */}
      <path d="M96 18c8-6 22-6 30 0" stroke="#E8702A" strokeWidth="2.2" strokeLinecap="round" strokeDasharray="1 5" />
    </svg>
  )
}
