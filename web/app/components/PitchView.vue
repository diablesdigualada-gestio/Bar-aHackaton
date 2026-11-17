<!-- Pitch view with playback, the current state in words and a legend. Owner: Carles. -->
<script setup lang="ts">
const props = defineProps<{
  tracking: {
    step: number
    team_of_slot: number[]
    pitch: [number, number]
    ball: [number, number][]
    players: [number, number][][]
  }
  fps: number
  halves: [number, number][]
  timeline: string
  timelineStep: number
  home: string
  away: string
  jumpTo: number | null
}>()
const emit = defineEmits<{ frame: [frame: number] }>()

const MISSING = -99
const BADGE = { H: 'error', A: 'info', D: 'neutral' } as const
const SPEEDS = [1, 4, 10]
const index = ref(Math.round((props.halves[0]?.[0] ?? 0) / props.tracking.step))
const playing = ref(false)
const speed = ref(1)
let handle = 0
let last = 0

const length = computed(() => props.tracking.pitch[0])
const width = computed(() => props.tracking.pitch[1])
const maxIndex = computed(() => props.tracking.ball.length - 1)
const frame = computed(() => index.value * props.tracking.step)

// Only the points that exist on this sample, so missing slots are never drawn.
const players = computed(() => (props.tracking.players[index.value] ?? [])
  .map((p, slot) => ({ x: p[0], y: p[1], team: props.tracking.team_of_slot[slot] }))
  .filter(p => p.x !== MISSING))
const ball = computed(() => {
  const b = props.tracking.ball[index.value]
  return b && b[0] !== MISSING ? { x: b[0], y: b[1] } : null
})

const label = computed(() =>
  props.timeline[Math.floor(frame.value / props.timelineStep)] as Label | undefined)
const clock = computed(() => matchClock(frame.value, props.halves, props.fps))

watch(frame, f => emit('frame', f), { immediate: true })

function tick(now: number) {
  if (!playing.value) return
  const perSample = 1000 * props.tracking.step / props.fps / speed.value
  if (now - last >= perSample) {
    index.value = Math.min(maxIndex.value, index.value + Math.floor((now - last) / perSample))
    last = now
    if (index.value >= maxIndex.value) playing.value = false
  }
  handle = requestAnimationFrame(tick)
}

function toggle() {
  playing.value = !playing.value
  if (playing.value) {
    last = performance.now()
    handle = requestAnimationFrame(tick)
  } else {
    cancelAnimationFrame(handle)
  }
}

watch(() => props.jumpTo, (f) => {
  if (f === null) return
  index.value = Math.max(0, Math.min(maxIndex.value, Math.round(f / props.tracking.step)))
})

onBeforeUnmount(() => cancelAnimationFrame(handle))
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <UBadge size="lg" variant="solid" :color="BADGE[label ?? 'D']" icon="i-lucide-circle-dot">
        {{ stateSentence(label, home, away) }}
      </UBadge>
      <span class="text-sm tabular-nums text-muted">{{ clock }}</span>
    </div>

    <svg :viewBox="`-3 -3 ${length + 6} ${width + 6}`" class="w-full rounded bg-[#3f8f4f]"
         role="img" :aria-label="`Pitch at ${clock}: ${stateSentence(label, home, away)}`">
      <g fill="none" stroke="white" stroke-width="0.25">
        <rect x="0" y="0" :width="length" :height="width" />
        <line :x1="length / 2" y1="0" :x2="length / 2" :y2="width" />
        <circle :cx="length / 2" :cy="width / 2" r="9.15" />
        <rect x="0" :y="(width - 40.3) / 2" width="16.5" height="40.3" />
        <rect :x="length - 16.5" :y="(width - 40.3) / 2" width="16.5" height="40.3" />
        <rect x="0" :y="(width - 18.3) / 2" width="5.5" height="18.3" />
        <rect :x="length - 5.5" :y="(width - 18.3) / 2" width="5.5" height="18.3" />
      </g>
      <circle v-for="(p, i) in players" :key="i" :cx="p.x" :cy="p.y" r="1.3"
              :fill="p.team === 0 ? COLOURS.H : COLOURS.A" stroke="white" stroke-width="0.25" />
      <circle v-if="ball" :cx="ball.x" :cy="ball.y" r="0.8" fill="#facc15" stroke="black"
              stroke-width="0.2" />
      <text v-if="!players.length" :x="length / 2" :y="width / 2 + 1.2" text-anchor="middle"
            fill="white" font-size="3">No players on the pitch at this moment</text>
    </svg>

    <div class="flex items-center gap-3">
      <UButton :icon="playing ? 'i-lucide-pause' : 'i-lucide-play'" size="sm"
               :aria-label="playing ? 'Pause' : 'Play'" @click="toggle" />
      <USlider v-model="index" :min="0" :max="maxIndex" class="flex-1" aria-label="Match time" />
      <UFieldGroup size="xs">
        <UButton v-for="s in SPEEDS" :key="s" :variant="speed === s ? 'solid' : 'outline'"
                 color="neutral" :aria-label="`Speed x${s}`" @click="speed = s">x{{ s }}</UButton>
      </UFieldGroup>
    </div>

    <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      <span class="inline-flex items-center gap-1">
        <span class="size-3 rounded-full" :style="{ background: COLOURS.H }" />{{ home }} players
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="size-3 rounded-full" :style="{ background: COLOURS.A }" />{{ away }} players
      </span>
      <span class="inline-flex items-center gap-1">
        <span class="size-2.5 rounded-full bg-[#facc15]" />Ball
        <template v-if="!ball">(not seen by the cameras right now)</template>
      </span>
    </div>
  </div>
</template>
