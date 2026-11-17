<!--
  Main page: load match.json, show the summary, the possession strips and the spell list.
  Owner: Carles.
-->
<script setup lang="ts">
interface Spell { label: 'H' | 'A' | 'D', start: number, end: number, seconds: number }
interface MatchFile {
  summary: {
    home: string, away: string
    possession_home: number, possession_away: number, ball_in_play: number
    spells: Record<string, number>
  }
  spells: Spell[]
  fps: number
  halves: [number, number][]
  timeline_step: number
  timeline: string
  tracking?: {
    step: number
    team_of_slot: number[]
    pitch: [number, number]
    ball: [number, number][]
    players: [number, number][][]
  }
}

const match = ref<MatchFile | null>(null)
const error = ref('')
const picked = ref<number | null>(null)
const filter = ref<'all' | 'H' | 'A' | 'D'>('all')
const input = ref<HTMLInputElement | null>(null)

// The JSON holds match data, so it is never in the repo: either web/public/match.json written by
// run.py --viewer on this machine, or a file chosen by hand.
onMounted(async () => {
  try {
    const res = await fetch('/match.json')
    if (res.ok) match.value = await res.json()
  } catch {
    // nothing to load yet, the button is there for that
  }
})

async function onFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    match.value = JSON.parse(await file.text())
    error.value = ''
  } catch {
    error.value = 'That file is not a viewer JSON.'
  }
}

function clock(frame: number) {
  const fps = match.value?.fps ?? 25
  const s = Math.floor(frame / fps)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

const percent = (x: number) => `${(100 * x).toFixed(1)}%`
const LABEL_COLOUR = { H: 'error', A: 'info', D: 'neutral' } as const

const visibleSpells = computed(() => {
  const all = match.value?.spells ?? []
  return (filter.value === 'all' ? all : all.filter(s => s.label === filter.value)).slice(0, 400)
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex gap-3 items-center">
      <UButton icon="i-lucide-upload" @click="input?.click()">Load match.json</UButton>
      <input ref="input" type="file" accept=".json" class="hidden" @change="onFile">
      <span v-if="error" class="text-error text-sm">{{ error }}</span>
      <span v-else-if="!match" class="text-muted text-sm">
        Run <code>python run.py --viewer</code> or pick the file by hand.
      </span>
    </div>

    <template v-if="match">
      <div class="grid gap-4 md:grid-cols-3">
        <UCard>
          <p class="text-sm text-muted">Possession in live play</p>
          <p class="mt-1 font-semibold">
            {{ match.summary.home }} {{ percent(match.summary.possession_home) }}
            <span class="text-muted">vs</span>
            {{ match.summary.away }} {{ percent(match.summary.possession_away) }}
          </p>
          <UProgress :model-value="100 * match.summary.possession_home" color="error" class="mt-3" />
        </UCard>
        <UCard>
          <p class="text-sm text-muted">Ball in play</p>
          <p class="mt-1 text-2xl font-semibold">{{ percent(match.summary.ball_in_play) }}</p>
        </UCard>
        <UCard>
          <p class="text-sm text-muted">Spells</p>
          <div class="mt-2 flex gap-2">
            <UBadge color="error">H {{ match.summary.spells.H }}</UBadge>
            <UBadge color="info">A {{ match.summary.spells.A }}</UBadge>
            <UBadge color="neutral">D {{ match.summary.spells.D }}</UBadge>
          </div>
        </UCard>
      </div>

      <UCard>
        <template #header>Timeline</template>
        <div v-for="(half, i) in match.halves" :key="i" class="mb-3">
          <p class="text-xs text-muted mb-1">Half {{ i + 1 }}</p>
          <PossessionStrip :timeline="match.timeline" :step="match.timeline_step"
                           :first="half[0]" :last="half[1]" @pick="picked = $event" />
        </div>
        <p v-if="picked !== null" class="text-sm">
          Frame {{ picked }}, video time {{ clock(picked) }}
        </p>
      </UCard>

      <UCard v-if="match.tracking">
        <template #header>Pitch</template>
        <PitchView :tracking="match.tracking" :fps="match.fps" :jump-to="picked" />
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <span>Possession spells</span>
            <div class="flex gap-1">
              <UButton v-for="f in ['all', 'H', 'A', 'D'] as const" :key="f" size="xs"
                       :variant="filter === f ? 'solid' : 'ghost'" @click="filter = f">
                {{ f }}
              </UButton>
            </div>
          </div>
        </template>
        <table class="w-full text-sm">
          <thead class="text-muted text-left">
            <tr><th>Team</th><th>Start</th><th>End</th><th>Seconds</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in visibleSpells" :key="s.start" class="border-t border-default
                cursor-pointer hover:bg-elevated" @click="picked = s.start">
              <td><UBadge :color="LABEL_COLOUR[s.label]" variant="subtle">{{ s.label }}</UBadge></td>
              <td>{{ clock(s.start) }}</td>
              <td>{{ clock(s.end) }}</td>
              <td>{{ s.seconds }}</td>
            </tr>
          </tbody>
        </table>
      </UCard>
    </template>
  </div>
</template>
