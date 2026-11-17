<!-- Pitch view with playback. Owner: Carles. -->
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
  jumpTo: number | null
}>()

const MISSING = -99
const index = ref(0)
const playing = ref(false)
let handle = 0
let last = 0

const length = computed(() => props.tracking.pitch[0])
const width = computed(() => props.tracking.pitch[1])
const maxIndex = computed(() => props.tracking.ball.length - 1)

// Only the points that exist on this sample, so missing slots are never drawn.
const players = computed(() => (props.tracking.players[index.value] ?? [])
  .map((p, slot) => ({ x: p[0], y: p[1], team: props.tracking.team_of_slot[slot] }))
  .filter(p => p.x !== MISSING))
const ball = computed(() => {
  const b = props.tracking.ball[index.value]
  return b && b[0] !== MISSING ? { x: b[0], y: b[1] } : null
})

const clock = computed(() => {
  const s = Math.floor(index.value * props.tracking.step / props.fps)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})

// Real speed: fps / step samples per second.
function tick(now: number) {
  if (!playing.value) return
  const perSample = 1000 * props.tracking.step / props.fps
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

watch(() => props.jumpTo, (frame) => {
  if (frame === null) return
  index.value = Math.max(0, Math.min(maxIndex.value, Math.round(frame / props.tracking.step)))
})

onBeforeUnmount(() => cancelAnimationFrame(handle))
</script>

<template>
  <div class="space-y-3">
    <svg :viewBox="`-3 -3 ${length + 6} ${width + 6}`" class="w-full rounded bg-[#3f8f4f]">
      <g fill="none" stroke="white" stroke-width="0.25">
        <rect x="0" y="0" :width="length" :height="width" />
        <line :x1="length / 2" y1="0" :x2="length / 2" :y2="width" />
        <circle :cx="length / 2" :cy="width / 2" r="9.15" />
        <rect x="0" :y="(width - 40.3) / 2" width="16.5" height="40.3" />
        <rect :x="length - 16.5" :y="(width - 40.3) / 2" width="16.5" height="40.3" />
        <rect x="0" :y="(width - 18.3) / 2" width="5.5" height="18.3" />
        <rect :x="length - 5.5" :y="(width - 18.3) / 2" width="5.5" height="18.3" />
      </g>
      <circle v-for="(p, i) in players" :key="i" :cx="p.x" :cy="p.y" r="1.1"
              :fill="p.team === 0 ? '#c8102e' : '#1f4e9c'" stroke="black" stroke-width="0.15" />
      <circle v-if="ball" :cx="ball.x" :cy="ball.y" r="0.7" fill="white" stroke="black"
              stroke-width="0.2" />
    </svg>
    <div class="flex items-center gap-3">
      <UButton :icon="playing ? 'i-lucide-pause' : 'i-lucide-play'" size="sm" @click="toggle" />
      <USlider v-model="index" :min="0" :max="maxIndex" class="flex-1" />
      <span class="text-sm tabular-nums w-14 text-right">{{ clock }}</span>
    </div>
  </div>
</template>
