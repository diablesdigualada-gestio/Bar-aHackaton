<!--
  One horizontal strip per half: every pixel column is a slice of the timeline coloured by label.
  Minute ticks underneath and a white marker where the pitch view currently is.
  Owner: Carles.
-->
<script setup lang="ts">
const props = defineProps<{
  timeline: string
  step: number
  first: number
  last: number
  fps: number
  offsetMinutes: number
  cursor: number | null
}>()
const emit = defineEmits<{ pick: [frame: number] }>()

const canvas = ref<HTMLCanvasElement | null>(null)

const ticks = computed(() => {
  const minutes = (props.last - props.first) / props.fps / 60
  const out = []
  for (let m = 0; m <= minutes; m += 15) {
    out.push({ left: `${(100 * m) / minutes}%`, text: `${m + props.offsetMinutes}'` })
  }
  return out
})

const marker = computed(() => {
  if (props.cursor === null || props.cursor < props.first || props.cursor > props.last) return null
  return `${(100 * (props.cursor - props.first)) / (props.last - props.first)}%`
})

function draw() {
  const el = canvas.value
  if (!el) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const width = el.clientWidth
  el.width = width
  const from = Math.floor(props.first / props.step)
  const to = Math.floor(props.last / props.step)
  const perPixel = (to - from) / width
  for (let x = 0; x < width; x++) {
    const label = (props.timeline[Math.floor(from + x * perPixel)] ?? 'D') as Label
    ctx.fillStyle = COLOURS[label] ?? COLOURS.D
    ctx.fillRect(x, 0, 1, el.height)
  }
}

function onClick(event: MouseEvent) {
  const el = canvas.value
  if (!el) return
  const ratio = event.offsetX / el.clientWidth
  emit('pick', Math.round(props.first + ratio * (props.last - props.first)))
}

onMounted(() => {
  draw()
  window.addEventListener('resize', draw)
})
onBeforeUnmount(() => window.removeEventListener('resize', draw))
watch(() => props.timeline, draw)
</script>

<template>
  <div>
    <div class="relative">
      <canvas ref="canvas" height="32" class="w-full rounded cursor-pointer block"
              title="Click to watch this moment on the pitch" @click="onClick" />
      <div v-if="marker" class="absolute -top-1 -bottom-1 w-0.5 bg-white shadow pointer-events-none"
           :style="{ left: marker }" />
    </div>
    <div class="relative h-4 mt-1 text-[11px] text-muted">
      <span v-for="t in ticks" :key="t.text" class="absolute -translate-x-1/2 first:translate-x-0"
            :style="{ left: t.left }">{{ t.text }}</span>
    </div>
  </div>
</template>
