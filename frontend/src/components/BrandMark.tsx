import { useId } from 'react';

interface BrandMarkProps {
  size?: number;
}

export function BrandMark({ size = 44 }: BrandMarkProps) {
  const id = useId().replace(/:/g, '');
  const bg = `bm-bg-${id}`;
  const rim = `bm-rim-${id}`;
  const up = `bm-up-${id}`;
  const down = `bm-down-${id}`;
  const glow = `bm-glow-${id}`;

  return (
    <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="MT5 Señales">
      <defs>
        <linearGradient id={bg} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1c2d50" />
          <stop offset="1" stopColor="#0a1020" />
        </linearGradient>
        <linearGradient id={rim} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" />
          <stop offset="0.6" stopColor="#818cf8" stopOpacity="0.7" />
          <stop offset="1" stopColor="#6366f1" stopOpacity="0.3" />
        </linearGradient>
        <linearGradient id={up} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4ade80" />
          <stop offset="1" stopColor="#10b981" />
        </linearGradient>
        <linearGradient id={down} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fb7185" />
          <stop offset="1" stopColor="#e11d48" />
        </linearGradient>
        <radialGradient id={glow} cx="0.8" cy="0.18" r="0.55">
          <stop offset="0" stopColor="#38bdf8" stopOpacity="0.4" />
          <stop offset="1" stopColor="#38bdf8" stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect x="0.75" y="0.75" width="46.5" height="46.5" rx="12" fill={`url(#${bg})`} stroke={`url(#${rim})`} strokeWidth="1.5" />
      <rect x="0.75" y="0.75" width="46.5" height="46.5" rx="12" fill={`url(#${glow})`} />

      <path d="M8 40 H40" stroke="#475569" strokeWidth="1.2" strokeLinecap="round" />

      <path d="M13 24 V37" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" />
      <rect x="9.5" y="27" width="7" height="8" rx="1.8" fill={`url(#${up})`} />

      <path d="M23 16 V33" stroke="#fb7185" strokeWidth="2" strokeLinecap="round" />
      <rect x="19.5" y="19" width="7" height="10" rx="1.8" fill={`url(#${down})`} />

      <path d="M33 12 V31" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" />
      <rect x="29.5" y="14.5" width="7" height="13.5" rx="1.8" fill={`url(#${up})`} />

      <circle cx="39.5" cy="8.5" r="5.2" fill="none" stroke="#38bdf8" strokeOpacity="0.45" strokeWidth="1.2" />
      <circle cx="39.5" cy="8.5" r="2.6" fill="#38bdf8" />
      <circle cx="39.5" cy="8.5" r="1.1" fill="#f0f9ff" />
    </svg>
  );
}
