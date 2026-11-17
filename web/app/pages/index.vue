<!--
  Main page: summary in plain words, the match timeline, the pitch and the list of possessions.
  Owner: Carles.
-->
<script setup lang="ts">
interface Spell { label: Label, start: number, end: number, seconds: number }
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
const loading = ref(true)
const error = ref('')
const picked = ref<number | null>(null)
const current = ref<number | null>(null)
const filter = ref<'all' | Label>('all')
const input = ref<HTMLInputElement | null>(null)
const pitchCard = ref<{ $el: HTMLElement } | null>(null)

// The JSON holds match data, so it is never in the repo: either web/public/match.json written by
// run.py --viewer on this machine, or a file chosen by hand.
onMounted(async () => {
  try {
    const res = await fetch('/match.json')
    if (res.ok) match.value = await res.json()
  } catch {
    // nothing to load yet, the empty state explains what to do
  }
  loading.value = false
})

async function onFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    match.value = JSON.parse(await file.text())
    error.value = ''
  } catch {
    error.value = 'That file is not a viewer file. Pick the match.json written by run.py --viewer.'
  }
}

const home = computed(() => match.value?.summary.home ?? 'Home')
const away = computed(() => match.value?.summary.away ?? 'Away')
const fps = computed(() => match.value?.fps ?? 25)
const halves = computed(() => match.value?.halves ?? [])
const at = (frame: number) => matchClock(frame, halves.value, fps.value)
const percent = (x: number) => `${Math.round(100 * x)}%`

function watchMoment(frame: number) {
  picked.value = frame
  // Bring the pitch into view, otherwise a click far down the list changes something unseen.
  pitchCard.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const filterTabs = computed(() => [
  { label: 'All', value: 'all' },
  { label: home.value, value: 'H' },
  { label: away.value, value: 'A' },
  { label: 'Ball out of play', value: 'D' },
])

const visibleSpells = computed(() => {
  const all = match.value?.spells ?? []
  return filter.value === 'all' ? all : all.filter(s => s.label === filter.value)
})

const isCurrent = (s: Spell) => current.value !== null && current.value >= s.start
  && current.value < s.end

const columns = [
  { accessorKey: 'label', id: 'who', header: 'Who' },
  { accessorKey: 'start', id: 'from', header: 'From' },
  { accessorKey: 'end', id: 'to', header: 'To' },
  { accessorKey: 'seconds', id: 'duration', header: 'Duration' },
]

// The row being replayed on the pitch is highlighted.
const tableMeta = {
  class: { tr: (row: { original: Spell }) => (isCurrent(row.original) ? 'bg-elevated font-semibold' : '') },
}

function onSelect(row: { original: Spell }) {
  watchMoment(row.original.start)
}

const BADGE = { H: 'error', A: 'info', D: 'neutral' } as const
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="text-muted">Loading the match...</div>

    <UCard v-else-if="!match" class="max-w-xl mx-auto text-center">
      <p class="font-semibold text-lg">No match loaded yet</p>
      <p class="text-muted text-sm mt-2">
        Run <code>python run.py --team diables --viewer</code> and reload this page, or open the
        file it writes (<code>web/public/match.json</code>).
      </p>
      <UButton class="mt-4" icon="i-lucide-folder-open" @click="input?.click()">Open a match file</UButton>
      <p v-if="error" class="text-error text-sm mt-3">{{ error }}</p>
    </UCard>
    <input ref="input" type="file" accept=".json" class="hidden" @change="onFile">

    <template v-if="match">
      <div>
        <h2 class="text-2xl font-bold">
          <span class="text-[#c8102e] dark:text-[#ff6b7d]">{{ home }}</span>
          <span class="text-muted font-normal"> vs </span>
          <span class="text-[#1f4e9c] dark:text-[#7aa5e8]">{{ away }}</span>
        </h2>
        <p class="text-muted mt-1">
          Who had the ball, second by second, worked out automatically from the player and ball
          tracking.
        </p>
        <div class="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-sm">
          <span class="inline-flex items-center gap-2">
            <span class="w-5 h-3 rounded-sm" :style="{ background: COLOURS.H }" />{{ home }} has the ball
          </span>
          <span class="inline-flex items-center gap-2">
            <span class="w-5 h-3 rounded-sm" :style="{ background: COLOURS.A }" />{{ away }} has the ball
          </span>
          <span class="inline-flex items-center gap-2">
            <span class="w-5 h-3 rounded-sm" :style="{ background: COLOURS.D }" />Ball out of play
          </span>
        </div>
        <p class="text-xs text-muted mt-2 max-w-3xl">
          Laws of the Game (IFAB), as applied in LaLiga: the ball is out of play when it has
          wholly crossed the goal line or touchline, or when the referee has stopped play (Law 9),
          until the restart: kick-off, throw-in, goal kick, corner kick, free kick, penalty kick or
          dropped ball. A team keeps possession through passes and deflections; it only changes
          when the other team takes control of the ball.
        </p>
      </div>

      <div class="grid gap-4 md:grid-cols-3">
        <UCard>
          <p class="text-sm text-muted">Possession</p>
          <div class="mt-1 flex justify-between font-semibold text-lg">
            <span class="text-[#c8102e] dark:text-[#ff6b7d]">{{ percent(match.summary.possession_home) }}</span>
            <span class="text-[#1f4e9c] dark:text-[#7aa5e8]">{{ percent(match.summary.possession_away) }}</span>
          </div>
          <UProgress :model-value="100 * match.summary.possession_home" size="lg" class="mt-2"
                     :ui="{ base: 'bg-[#1f4e9c]', indicator: 'bg-[#c8102e]' }"
                     :aria-label="`${home} ${percent(match.summary.possession_home)}, ${away} ${percent(match.summary.possession_away)}`" />
          <div class="mt-1 flex justify-between text-xs text-muted">
            <span>{{ home }}</span><span>{{ away }}</span>
          </div>
        </UCard>
        <UCard>
          <p class="text-sm text-muted">Ball in play</p>
          <p class="mt-1 text-2xl font-semibold">{{ percent(match.summary.ball_in_play) }}</p>
          <p class="text-xs text-muted mt-1">
            of the two halves, added time included. The rest of the time play was stopped.
          </p>
        </UCard>
        <UCard>
          <p class="text-sm text-muted">Number of possessions</p>
          <div class="mt-1 flex justify-between text-2xl font-semibold">
            <span class="text-[#c8102e] dark:text-[#ff6b7d]">{{ match.summary.spells.H }}</span>
            <span class="text-[#1f4e9c] dark:text-[#7aa5e8]">{{ match.summary.spells.A }}</span>
          </div>
          <div class="flex justify-between text-xs text-muted">
            <span>{{ home }}</span><span>{{ away }}</span>
          </div>
          <p class="text-xs text-muted mt-1">and {{ match.summary.spells.D }} stoppages</p>
        </UCard>
      </div>

      <UCard>
        <template #header>
          <p class="font-semibold">Match timeline</p>
          <p class="text-sm text-muted">
            Each coloured band is one possession. Click anywhere to watch that moment on the pitch.
          </p>
        </template>
        <div v-for="(half, i) in match.halves" :key="i" class="mb-4 last:mb-0">
          <p class="text-sm font-medium mb-1">{{ i === 0 ? 'First half' : 'Second half' }}</p>
          <PossessionStrip :timeline="match.timeline" :step="match.timeline_step"
                           :first="half[0]" :last="half[1]" :fps="match.fps"
                           :offset-minutes="45 * i" :cursor="current" @pick="watchMoment" />
        </div>
      </UCard>

      <UCard v-if="match.tracking" ref="pitchCard" class="scroll-mt-4">
        <template #header>
          <p class="font-semibold">Pitch</p>
          <p class="text-sm text-muted">
            Press play to replay the match from the tracking data. The white line on the timeline
            shows where you are.
          </p>
        </template>
        <PitchView :tracking="match.tracking" :fps="match.fps" :halves="match.halves"
                   :timeline="match.timeline" :timeline-step="match.timeline_step"
                   :home="home" :away="away" :jump-to="picked" @frame="current = $event" />
      </UCard>

      <UCard>
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p class="font-semibold">All possessions</p>
              <p class="text-sm text-muted">Click a row to watch it on the pitch.</p>
            </div>
            <UTabs v-model="filter" :items="filterTabs" :content="false" size="xs" />
          </div>
        </template>
        <UTable :data="visibleSpells" :columns="columns" :meta="tableMeta" sticky
                class="max-h-96" @select="onSelect">
          <template #who-cell="{ row }">
            <UBadge :color="BADGE[row.original.label as Label]" variant="subtle">
              {{ whoName(row.original.label, home, away) }}
            </UBadge>
          </template>
          <template #from-cell="{ row }">
            <span class="tabular-nums">{{ at(row.original.start) }}</span>
          </template>
          <template #to-cell="{ row }">
            <span class="tabular-nums">{{ at(row.original.end) }}</span>
          </template>
          <template #duration-cell="{ row }">
            <span class="tabular-nums">{{ duration(row.original.seconds) }}</span>
          </template>
        </UTable>
        <p class="text-xs text-muted mt-2">{{ visibleSpells.length }} shown</p>
      </UCard>

      <div class="text-right">
        <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-folder-open"
                 @click="input?.click()">Open another match file</UButton>
      </div>
    </template>
  </div>
</template>
