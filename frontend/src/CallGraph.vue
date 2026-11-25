<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import CallGraphNode from './CallGraphNode.vue'
import { projectCalls, rootOf, type CallGraph, type GraphNode } from './callGraph'
import { drawWires, layoutWires, wireGutterHeight, type AxisBox, type FlowDirection, type NodeBox, type WireColors } from './graphWires'

const props = defineProps<{
  graph: CallGraph
  roots: GraphNode[]
  rootFilter: string
  selectedId: string
  colorScheme: 'light' | 'dark'
}>()
const emit = defineEmits<{ select: [id: string]; clear: [] }>()

const minimumZoom = .01
const maximumZoom = 2
const zoomStep = 1.2
const expanded = ref(new Set<string>())
const zoom = ref(1)
const dragging = ref(false)
const direction = ref<FlowDirection>('horizontal')
const vertical = computed(() => direction.value === 'vertical')
const viewport = ref<HTMLDivElement | null>(null)
const board = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const collapsed = computed(() => projectCalls(props.graph, new Set()))
const projection = computed(() =>
  expanded.value.size || props.selectedId ? projectCalls(props.graph, expanded.value, props.selectedId) : collapsed.value,
)
const emphasizedWires = computed(() => {
  const { selectedId, rootFilter } = props
  if (!selectedId && !rootFilter) return null
  return new Set(projection.value.edges.filter(edge => selectedId
    ? edge.selected
    : rootOf(edge.source).id === rootFilter || rootOf(edge.target).id === rootFilter,
  ))
})
const allContainers = computed(() => {
  const containers = new Set<string>()
  const pending = [...props.roots]
  while (pending.length) {
    const node = pending.pop()!
    if (!node.children.length) continue
    containers.add(node.id)
    pending.push(...node.children)
  }
  return containers
})
const mutedNodes = computed(() => {
  const { selectedId, rootFilter } = props
  const muted = new Set<string>()
  if (!selectedId && !rootFilter) return muted

  const relatedNodes = new Set<string>()
  function markAncestors(id: string) {
    for (let node = props.graph.functions.get(id); node; node = node.parent ?? undefined) {
      relatedNodes.add(node.id)
    }
  }

  if (selectedId) {
    markAncestors(selectedId)
    for (const call of props.graph.calls) {
      if (call.caller === selectedId) markAncestors(call.target)
      if (call.target === selectedId) markAncestors(call.caller)
    }
  }

  for (const root of props.roots) {
    const pending = [root]
    while (pending.length) {
      const node = pending.pop()!
      if (selectedId ? !relatedNodes.has(node.id) : root.id !== rootFilter) muted.add(node.id)
      pending.push(...node.children)
    }
  }
  return muted
})
const hasDetours = computed(() => {
  if (vertical.value) return collapsed.value.edges.length > 0
  const order = new Map(props.roots.map((node, index) => [node.id, index]))
  return collapsed.value.edges.some(({ source, target }) =>
    Math.abs(order.get(source.id)! - order.get(target.id)!) > 1,
  )
})
let wires: ReturnType<typeof layoutWires> = []
let observer: ResizeObserver | undefined
let frame = 0
let measure = true
let wireColors: WireColors | undefined
let pan: { pointerId: number; x: number; y: number; left: number; top: number } | undefined

function draw() {
  frame = 0
  const surface = canvas.value
  const scroll = viewport.value
  const content = board.value
  const context = surface?.getContext('2d')
  if (!surface || !context || !scroll || !content) return
  const width = scroll.clientWidth
  const height = scroll.clientHeight
  const scale = Math.min(window.devicePixelRatio || 1, 2)
  const pixelWidth = Math.round(width * scale)
  const pixelHeight = Math.round(height * scale)
  if (surface.width !== pixelWidth || surface.height !== pixelHeight) {
    surface.width = pixelWidth
    surface.height = pixelHeight
    surface.style.width = `${width}px`
    surface.style.height = `${height}px`
  }
  if (measure) {
    measure = false
    const origin = content.getBoundingClientRect()
    const boxes = new Map<string, NodeBox>()
    function measureBox(rect: DOMRect): AxisBox {
      const left = (rect.left - origin.left) / zoom.value
      const top = (rect.top - origin.top) / zoom.value
      const width = rect.width / zoom.value
      const height = rect.height / zoom.value
      return vertical.value
        ? { start: top, end: top + height, crossStart: left, crossEnd: left + width }
        : { start: left, end: left + width, crossStart: top, crossEnd: top + height }
    }
    content.querySelectorAll<HTMLDivElement>('.graph-lane').forEach((element, index) => {
      const lane = { ...measureBox(element.getBoundingClientRect()), index }
      element.querySelectorAll<HTMLButtonElement>('[data-graph-node]').forEach(header => {
        boxes.set(header.dataset.graphNode!, { ...measureBox(header.getBoundingClientRect()), lane })
      })
    })
    wires = layoutWires(projection.value.edges, boxes, direction.value)
  }
  if (!wireColors) {
    const styles = getComputedStyle(content)
    wireColors = {
      stroke: styles.getPropertyValue('--graph-wire').trim(),
      activeStroke: styles.getPropertyValue('--graph-wire-active').trim(),
      labelBackground: styles.getPropertyValue('--canvas').trim(),
      labelText: styles.getPropertyValue('--text').trim(),
    }
  }
  context.resetTransform()
  context.clearRect(0, 0, pixelWidth, pixelHeight)
  const drawScale = scale * zoom.value
  context.scale(drawScale, drawScale)
  drawWires(context, wires, {
    left: scroll.scrollLeft / zoom.value,
    top: scroll.scrollTop / zoom.value,
    width: width / zoom.value,
    height: height / zoom.value,
  }, wireColors, emphasizedWires.value)
}

function queueDraw() {
  if (!frame) frame = requestAnimationFrame(draw)
}

function updateLayout() {
  measure = true
  queueDraw()
}

function toggle(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

function collapseAll() {
  expanded.value.clear()
  viewport.value?.scrollTo(0, 0)
}

function expandAll() {
  expanded.value = new Set(allContainers.value)
}

function setZoom(requested: number, anchor?: { x: number; y: number }) {
  const scroll = viewport.value
  if (!scroll) return
  const next = Math.min(maximumZoom, Math.max(minimumZoom, requested))
  if (next === zoom.value) return
  const point = anchor ?? { x: scroll.clientWidth / 2, y: scroll.clientHeight / 2 }
  const x = (scroll.scrollLeft + point.x) * next / zoom.value
  const y = (scroll.scrollTop + point.y) * next / zoom.value
  zoom.value = next
  void nextTick(() => {
    scroll.scrollTo(x - point.x, y - point.y)
    updateLayout()
  })
}

function fitView() {
  const scroll = viewport.value
  const content = board.value
  if (!scroll || !content) return
  const lanes = Array.from(content.children, lane => lane.getBoundingClientRect())
  if (!lanes.length) return
  const styles = getComputedStyle(content)
  const width = (Math.max(...lanes.map(lane => lane.right)) - Math.min(...lanes.map(lane => lane.left))) / zoom.value
    + parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight)
  const height = (Math.max(...lanes.map(lane => lane.bottom)) - Math.min(...lanes.map(lane => lane.top))) / zoom.value
    + parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom)
  const desired = Math.min(1, (scroll.clientWidth - 2) / width, (scroll.clientHeight - 2) / height)
  setZoom(desired, { x: 0, y: 0 })
  void nextTick(() => scroll.scrollTo(0, 0))
}

function resetView() {
  setZoom(1, { x: 0, y: 0 })
  void nextTick(() => viewport.value?.scrollTo(0, 0))
}

function zoomOnWheel(event: WheelEvent) {
  const scroll = viewport.value
  if (!scroll || (!event.ctrlKey && !event.metaKey) || !event.deltaY) return
  event.preventDefault()
  const bounds = scroll.getBoundingClientRect()
  setZoom(zoom.value * (event.deltaY < 0 ? zoomStep : 1 / zoomStep), {
    x: event.clientX - bounds.left, y: event.clientY - bounds.top,
  })
}

function startPan(event: PointerEvent) {
  const scroll = viewport.value
  if (!scroll || event.button !== 0 || event.pointerType === 'touch'
    || !(event.target instanceof Element) || event.target.closest('button')) return
  const bounds = scroll.getBoundingClientRect()
  if (event.clientX - bounds.left >= scroll.clientWidth || event.clientY - bounds.top >= scroll.clientHeight) return
  pan = {
    pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: scroll.scrollLeft, top: scroll.scrollTop,
  }
  scroll.setPointerCapture(event.pointerId)
  event.preventDefault()
}

function movePan(event: PointerEvent) {
  if (!pan || pan.pointerId !== event.pointerId) return
  const x = event.clientX - pan.x
  const y = event.clientY - pan.y
  if (!dragging.value && Math.hypot(x, y) < 4) return
  dragging.value = true
  viewport.value?.scrollTo(pan.left - x, pan.top - y)
}

function finishPan(event: PointerEvent) {
  if (!pan || pan.pointerId !== event.pointerId) return
  if (event.type === 'pointerup' && !dragging.value) emit('clear')
  pan = undefined
  dragging.value = false
}

async function revealFunction(id: string) {
  const node = props.graph.functions.get(id)
  if (!node) return
  for (let parent = node.parent; parent; parent = parent.parent) expanded.value.add(parent.id)
  await nextTick()
  scrollToNode(node.id)
}

function scrollToNode(id: string) {
  const header = board.value?.querySelector<HTMLButtonElement>(`[data-graph-node="${CSS.escape(id)}"]`)
  const scroll = viewport.value
  if (!header || !scroll) return
  const rect = header.getBoundingClientRect()
  const bounds = scroll.getBoundingClientRect()
  const left = rect.left - bounds.left
  const top = rect.top - bounds.top
  if (left < 0 || rect.right > bounds.left + scroll.clientWidth
    || top < 0 || rect.bottom > bounds.top + scroll.clientHeight) {
    scroll.scrollBy(left - (scroll.clientWidth - rect.width) / 2, top - (scroll.clientHeight - rect.height) / 2)
  }
}

defineExpose({ revealFunction, revealRoot: scrollToNode })
watch(() => props.graph, () => {
  collapseAll()
  resetView()
})
watch(projection, updateLayout, { flush: 'post' })
watch(direction, () => {
  viewport.value?.scrollTo(0, 0)
  const selected = props.graph.functions.get(props.selectedId)
  if (selected) scrollToNode(selected.id)
  updateLayout()
}, { flush: 'post' })
watch(emphasizedWires, queueDraw, { flush: 'post' })
watch(() => props.colorScheme, () => {
  wireColors = undefined
  queueDraw()
}, { flush: 'post' })
onMounted(() => {
  observer = new ResizeObserver(updateLayout)
  if (board.value) observer.observe(board.value)
  if (viewport.value) observer.observe(viewport.value)
  updateLayout()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  if (frame) cancelAnimationFrame(frame)
})
</script>

<template>
  <section class="graph-panel" aria-labelledby="map-heading">
    <div class="graph-toolbar">
      <div class="graph-heading">
        <h2 id="map-heading">项目调用图</h2>
        <p class="map-legend">调用者 {{ vertical ? '↓' : '→' }} 被调用者，数字表示调用点数</p>
      </div>
      <div class="graph-toolbar-actions">
        <div class="graph-direction" role="group" aria-label="布局方向">
          <button type="button" :aria-pressed="!vertical" @click="direction = 'horizontal'">从左到右</button>
          <button type="button" :aria-pressed="vertical" @click="direction = 'vertical'">从上到下</button>
        </div>
        <div v-if="$slots.actions" class="graph-drawer-actions">
          <slot name="actions" />
        </div>
      </div>
    </div>
    <div class="graph-stage">
      <div
        ref="viewport"
        class="graph-viewport"
        :class="{ 'graph-viewport-dragging': dragging }"
        tabindex="0"
        aria-label="分层调用图画布"
        @scroll.passive="queueDraw"
        @wheel="zoomOnWheel"
        @pointerdown="startPan"
        @pointermove="movePan"
        @pointerup="finishPan"
        @pointercancel="finishPan"
        @lostpointercapture="finishPan"
      >
        <div
          ref="board"
          class="graph-board"
          :class="{ 'graph-board-vertical': vertical }"
          :style="{ '--wire-gutter': hasDetours ? `${wireGutterHeight}px` : undefined, zoom }"
        >
          <div v-for="(node, index) in roots" :key="node.id" class="graph-lane" :data-graph-tone="index % 5">
            <CallGraphNode
              :node="node"
              :expanded="expanded"
              :internal-counts="projection.internalCounts"
              :selected-id="selectedId"
              :muted-nodes="mutedNodes"
              @toggle="toggle"
              @select="emit('select', $event)"
            />
          </div>
        </div>
      </div>
      <canvas ref="canvas" class="graph-wires" aria-hidden="true"></canvas>
    </div>
    <div class="graph-view-tools">
      <div class="graph-zoom" role="group" aria-label="画布缩放">
        <button type="button" aria-label="缩小" title="缩小" :disabled="zoom <= minimumZoom" @click="setZoom(zoom / zoomStep)">−</button>
        <button type="button" aria-label="重置视图" title="重置视图" @click="resetView">{{ Math.round(zoom * 100) }}%</button>
        <button type="button" aria-label="放大" title="放大" :disabled="zoom >= maximumZoom" @click="setZoom(zoom * zoomStep)">+</button>
      </div>
      <button class="secondary" type="button" @click="fitView">适应画布</button>
      <button class="secondary" type="button" :disabled="expanded.size === allContainers.size" @click="expandAll">展开全部</button>
      <button class="secondary" type="button" :disabled="expanded.size === 0" @click="collapseAll">折叠全部</button>
    </div>
  </section>
</template>

<style scoped>
.graph-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  padding: 6px 8px;
}
.graph-toolbar {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-bottom: 7px;
}
.graph-heading, .graph-toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.graph-drawer-actions { display: flex; flex: none; gap: 4px; }
.graph-toolbar h2 { margin: 0; }
.graph-toolbar-actions :deep(button) { white-space: nowrap; }
.graph-toolbar button, .graph-view-tools button { font-size: .8rem; }
.graph-direction, .graph-zoom {
  display: flex;
  flex: none;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: var(--surface-subtle);
}
.graph-direction button, .graph-zoom button {
  border: 0;
  border-radius: 4px;
  padding: 6px 8px;
  color: var(--muted);
  background: transparent;
}
.graph-direction button:hover, .graph-zoom button:hover { background: var(--surface-hover); }
.graph-direction button[aria-pressed="true"] {
  color: var(--accent);
  background: var(--surface-active);
  font-weight: 650;
}
.map-legend { margin: 0; color: var(--muted); font-size: .78rem; }
.graph-stage {
  position: relative;
  isolation: isolate;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--line-strong);
  border-radius: 9px;
  background-color: var(--canvas);
  background-image: radial-gradient(var(--canvas-dot) 1px, transparent 1px);
  background-size: 18px 18px;
  overflow: hidden;
}
.graph-viewport { height: 100%; overflow: auto; cursor: grab; }
.graph-viewport-dragging { cursor: grabbing; user-select: none; }
.graph-viewport:focus-visible { outline: 2px solid var(--accent); outline-offset: -3px; }
.graph-board {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 236px;
  justify-content: start;
  align-items: start;
  gap: 48px;
  width: max-content;
  min-width: 100%;
  padding: var(--wire-gutter, 26px) 54px 28px 24px;
}
.graph-board-vertical {
  grid-auto-flow: row;
  grid-template-columns: minmax(156px, 290px);
  justify-content: center;
  width: 100%;
  min-width: calc(216px + var(--wire-gutter, 24px));
  padding: 26px 60px 42px var(--wire-gutter, 24px);
}
.graph-wires { position: absolute; z-index: 1; top: 0; left: 0; pointer-events: none; }
.graph-view-tools { display: flex; flex: none; align-items: center; flex-wrap: wrap; gap: 6px; padding-top: 7px; }
.graph-view-tools .secondary { padding: 6px 8px; }
.graph-zoom button:nth-child(2) { min-width: 45px; font-variant-numeric: tabular-nums; }
</style>
