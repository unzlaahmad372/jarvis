/**
 * JarvisCore — animated SVG orb that reflects JARVIS state.
 *
 * States: IDLE | LISTENING | THINKING | SPEAKING | ERROR | OFFLINE
 *
 * Uses CSS animations only — no canvas, no WebGL.
 * Respects prefers-reduced-motion.
 */

import styles from './JarvisCore.module.css'

export type CoreState =
  | 'IDLE'
  | 'LISTENING'
  | 'THINKING'
  | 'SPEAKING'
  | 'ERROR'
  | 'OFFLINE'

const STATE_LABELS: Record<CoreState, string> = {
  IDLE:      'STANDBY',
  LISTENING: 'LISTENING',
  THINKING:  'PROCESSING',
  SPEAKING:  'RESPONDING',
  ERROR:     'ERROR',
  OFFLINE:   'OFFLINE',
}

const STATE_COLORS: Record<CoreState, string> = {
  IDLE:      'var(--hud-accent-muted)',
  LISTENING: 'var(--hud-success)',
  THINKING:  'var(--hud-accent)',
  SPEAKING:  'var(--hud-info)',
  ERROR:     'var(--hud-danger)',
  OFFLINE:   'var(--hud-text-dim)',
}

interface JarvisCoreProps {
  state?: CoreState
  size?: number
}

export function JarvisCore({ state = 'IDLE', size = 220 }: JarvisCoreProps) {
  const color = STATE_COLORS[state]
  const label = STATE_LABELS[state]
  const cx = size / 2
  const cy = size / 2

  // Ring radii
  const r1 = size * 0.42   // outer ring
  const r2 = size * 0.33   // mid ring
  const r3 = size * 0.24   // inner ring
  const r4 = size * 0.14   // core circle

  const isActive = state !== 'IDLE' && state !== 'OFFLINE'
  const isError  = state === 'ERROR'

  return (
    <div
      className={`${styles.wrapper} ${styles[`state_${state}`]}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`JARVIS status: ${label}`}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden="true"
        className={styles.svg}
      >
        <defs>
          {/* Radial glow gradient */}
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </radialGradient>

          {/* Arc clip for dashed segments */}
          <filter id="blur2">
            <feGaussianBlur stdDeviation="2" />
          </filter>
        </defs>

        {/* Background glow */}
        <circle cx={cx} cy={cy} r={r1 + 10} fill="url(#coreGlow)" />

        {/* Outer ring — slow rotation */}
        <g
          className={`${styles.ring} ${styles.ringOuter} ${isActive ? styles.rotating : ''}`}
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        >
          {/* Dashed arc segments */}
          <circle
            cx={cx} cy={cy} r={r1}
            fill="none"
            stroke={color}
            strokeWidth="1"
            strokeOpacity="0.4"
            strokeDasharray="6 4"
          />
          {/* Bright tick marks at 0°, 90°, 180°, 270° */}
          {[0, 90, 180, 270].map((deg) => {
            const rad = (deg * Math.PI) / 180
            const x1 = cx + (r1 - 6) * Math.cos(rad)
            const y1 = cy + (r1 - 6) * Math.sin(rad)
            const x2 = cx + (r1 + 4) * Math.cos(rad)
            const y2 = cy + (r1 + 4) * Math.sin(rad)
            return (
              <line
                key={deg}
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={color}
                strokeWidth="2"
                strokeOpacity="0.8"
              />
            )
          })}
        </g>

        {/* Mid ring — counter-rotation */}
        <g
          className={`${styles.ring} ${styles.ringMid} ${isActive ? styles.counterRotating : ''}`}
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        >
          <circle
            cx={cx} cy={cy} r={r2}
            fill="none"
            stroke={color}
            strokeWidth="1.5"
            strokeOpacity="0.5"
            strokeDasharray="12 6 3 6"
          />
          {/* Small arc highlight */}
          <circle
            cx={cx} cy={cy} r={r2}
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeOpacity="0.9"
            strokeDasharray={`${r2 * 0.6} ${r2 * 10}`}
            strokeLinecap="round"
          />
        </g>

        {/* Inner ring — fast rotation when active */}
        <g
          className={`${styles.ring} ${styles.ringInner} ${isActive ? styles.rotatingFast : ''}`}
          style={{ transformOrigin: `${cx}px ${cy}px` }}
        >
          <circle
            cx={cx} cy={cy} r={r3}
            fill="none"
            stroke={color}
            strokeWidth="1"
            strokeOpacity="0.35"
            strokeDasharray="4 8"
          />
        </g>

        {/* Core circle */}
        <circle
          cx={cx} cy={cy} r={r4}
          fill={color}
          fillOpacity={isError ? '0.6' : '0.15'}
          stroke={color}
          strokeWidth="1.5"
          strokeOpacity="0.9"
          className={isActive ? styles.corePulse : ''}
        />

        {/* Inner glow dot */}
        <circle
          cx={cx} cy={cy} r={r4 * 0.45}
          fill={color}
          fillOpacity={isActive ? '0.7' : '0.3'}
          filter="url(#blur2)"
        />

        {/* Thinking arc sweep */}
        {state === 'THINKING' && (
          <circle
            cx={cx} cy={cy} r={r2 + 4}
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeOpacity="0.6"
            strokeDasharray={`${(r2 + 4) * 0.8} ${(r2 + 4) * 10}`}
            strokeLinecap="round"
            className={styles.thinkingSweep}
            style={{ transformOrigin: `${cx}px ${cy}px` }}
          />
        )}

        {/* Listening pulse rings */}
        {state === 'LISTENING' && (
          <>
            <circle cx={cx} cy={cy} r={r1 + 8}  fill="none" stroke={color} strokeWidth="1" strokeOpacity="0.3" className={styles.pulseRing1} />
            <circle cx={cx} cy={cy} r={r1 + 18} fill="none" stroke={color} strokeWidth="1" strokeOpacity="0.15" className={styles.pulseRing2} />
          </>
        )}

        {/* Speaking wave bars */}
        {state === 'SPEAKING' && (
          <g className={styles.speakBars}>
            {[-12, -6, 0, 6, 12].map((offset, i) => (
              <rect
                key={i}
                x={cx + offset - 1.5}
                y={cy - 8}
                width={3}
                height={16}
                rx={1.5}
                fill={color}
                fillOpacity="0.8"
                className={styles[`bar${i}`]}
              />
            ))}
          </g>
        )}
      </svg>

      {/* State label */}
      <div className={styles.label} aria-hidden="true" style={{ color }}>
        {label}
      </div>
    </div>
  )
}
