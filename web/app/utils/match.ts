// Shared helpers for the viewer: colours, plain-language names and the match clock. Owner: Carles.

export type Label = 'H' | 'A' | 'D'

export const COLOURS: Record<Label, string> = { H: '#c8102e', A: '#1f4e9c', D: '#9ca3af' }

/** Short name of who a label stands for. */
export function whoName(label: Label, home: string, away: string) {
  return label === 'H' ? home : label === 'A' ? away : 'Ball out of play'
}

/** Sentence for the current state, as a spectator would say it. */
export function stateSentence(label: Label | undefined, home: string, away: string) {
  if (label === 'H') return `${home} has the ball`
  if (label === 'A') return `${away} has the ball`
  return 'Ball out of play'
}

const pad = (n: number) => String(n).padStart(2, '0')

/**
 * Match time of a video frame, the way LaLiga broadcasts show it. Each half lasts 45 minutes
 * plus the time the referee adds (IFAB Law 7), so the clock stops at 45:00 or 90:00 and added
 * time is shown on top: "45+02:13".
 */
export function matchClock(frame: number, halves: [number, number][], fps: number) {
  for (let i = 0; i < halves.length; i++) {
    const [first, last] = halves[i]!
    if (frame >= first && frame <= last) {
      const elapsed = Math.floor((frame - first) / fps)
      const regular = 45 * 60
      const base = regular * i
      const name = i === 0 ? '1st half' : '2nd half'
      if (elapsed < regular) {
        const s = base + elapsed
        return `${name} ${pad(Math.floor(s / 60))}:${pad(s % 60)}`
      }
      const extra = elapsed - regular
      return `${name} ${(base + regular) / 60}+${pad(Math.floor(extra / 60))}:${pad(extra % 60)}`
    }
  }
  if (halves.length && frame < halves[0]![0]) return 'Before kickoff'
  if (halves.length > 1 && frame < halves[1]![0]) return 'Half-time'
  return 'After the final whistle'
}

/** Seconds as "1 min 05 s" or "42 s". */
export function duration(seconds: number) {
  const s = Math.round(seconds)
  return s >= 60 ? `${Math.floor(s / 60)} min ${pad(s % 60)} s` : `${s} s`
}
