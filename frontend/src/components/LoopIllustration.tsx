/** An explanatory illustration, deliberately separate from actual plan data. */
export function LoopIllustration({ dark = false }: { dark?: boolean }) {
  const ink = dark ? '#e8f1df' : '#355d43'
  const surface = dark ? '#315b47' : '#ffffff'
  return (
    <svg viewBox="0 0 420 260" role="img" aria-label="Illustration: three neighbourhood shops connected in a loop">
      <defs><marker id={dark ? 'loop-arrow-dark' : 'loop-arrow'} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="none" stroke={dark ? '#bed49e' : '#91ad7e'} strokeWidth="1.5" /></marker></defs>
      <circle cx="210" cy="136" r="92" fill="none" stroke={dark ? '#ffffff10' : '#dce5d6'} />
      <circle cx="210" cy="136" r="118" fill="none" stroke={dark ? '#ffffff08' : '#e9eee3'} />
      <g fill="none" stroke={dark ? '#bed49e' : '#91ad7e'} strokeWidth="1.6" strokeDasharray="5 5" markerEnd={`url(#${dark ? 'loop-arrow-dark' : 'loop-arrow'})`}>
        <path d="M220 60 C287 56 320 84 319 139" /><path d="M293 184 C253 226 196 225 151 190" /><path d="M113 145 C102 100 133 64 179 57" />
      </g>
      {[[210,55],[310,166],[112,166]].map(([x,y],i) => (
        <g key={i} transform={`translate(${x-39},${y-30})`}>
          <rect width="78" height="69" rx="15" fill={surface} stroke={dark ? '#6b896b' : '#d9e3d1'} />
          <path d="M23 31v19h32V31M20 30h38l-5-12H25z" fill="none" stroke={ink} strokeWidth="1.8" strokeLinejoin="round" />
          <path d="M30 19v11M39 19v11M48 19v11M34 50V38h10v12" fill="none" stroke={ink} strokeWidth="1.5" />
          <circle cx="65" cy="12" r="11" fill={dark ? '#d7e8b2' : '#eff5e5'} /><text x="65" y="16" textAnchor="middle" fill="#35523b" fontSize="10" fontWeight="700">{String.fromCharCode(65+i)}</text>
        </g>
      ))}
      <circle cx="210" cy="145" r="24" fill={dark ? '#d7e8b2' : '#e3edcf'} />
      <path d="M197 146a13 13 0 0 1 22-10l4 4m0-9v9h-9m9 8a13 13 0 0 1-22 10l-4-4m0 9v-9h9" fill="none" stroke="#35523b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
