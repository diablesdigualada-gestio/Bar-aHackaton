<!--
  One horizontal strip per half: every pixel column is a slice of the timeline coloured by label.
  Owner: Carles.
-->
<script setup lang="ts">
const props = defineProps<{
  timeline: string
  step: number
  first: number
  last: number
}>()
const emit = defineEmits<{ pick: [frame: number] }>()

const canvas = ref<HTMLCanvasElement | null>(null)
const COLOURS: Record<string, string> = { H: '#c8102e', A: '#1f4e9c', D: '#9ca3af' }

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
    const label = props.timeline[Math.floor(from + x * perPixel)] ?? 'D'
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

onMounted(draw)
watch(() => props.timeline, draw)
</script>

<template>
  <canvas ref="canvas" height="28" class="w-full rounded cursor-pointer" @click="onClick" />
</template>
