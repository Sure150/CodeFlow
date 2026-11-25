import type { VisibleCall } from './callGraph'

export type FlowDirection = 'horizontal' | 'vertical'

export interface AxisBox {
  start: number
  end: number
  crossStart: number
  crossEnd: number
}

export interface NodeBox extends AxisBox {
  lane: AxisBox & { index: number }
}

interface Point { x: number; y: number }
interface Wire {
  edge: VisibleCall
  points: Point[]
  label: Point
  curved: boolean
}

export interface WireColors {
  stroke: string
  activeStroke: string
  labelBackground: string
  labelText: string
}

const trackCount = 5
const trackStart = 18
const trackSpacing = 14
export const wireGutterHeight = trackStart + trackCount * trackSpacing + 4

function route(source: NodeBox, target: NodeBox, loop: boolean): Point[] {
  const fromY = (source.crossStart + source.crossEnd) / 2 + (loop ? -7 : 3)
  const toY = (target.crossStart + target.crossEnd) / 2 + (loop ? 7 : -3)
  if (source.end + 14 < target.start || target.end + 14 < source.start) {
    const forward = source.end < target.start
    const startX = forward ? source.end : source.start
    const endX = forward ? target.start - 1 : target.end + 1
    const middle = (startX + endX) / 2
    return [
      { x: startX, y: fromY }, { x: middle, y: fromY },
      { x: middle, y: toY }, { x: endX, y: toY },
    ]
  }

  const outside = Math.max(source.end, target.end) + (loop ? 43 : 25)
  return [
    { x: source.end, y: fromY }, { x: outside, y: fromY },
    { x: outside, y: toY }, { x: target.end + 1, y: toY },
  ]
}

function routeBesideLane(source: NodeBox, target: NodeBox, loop: boolean): Point[] {
  const from = (source.start + source.end) / 2 + (loop ? -7 : 3)
  const to = (target.start + target.end) / 2 + (loop ? 7 : -3)
  const side = source.lane.crossEnd + (loop ? 43 : 25)
  return [
    { x: from, y: source.crossEnd }, { x: from, y: side },
    { x: to, y: side }, { x: to, y: target.crossEnd + 1 },
  ]
}

function routeThroughGutter(source: NodeBox, target: NodeBox, track: number, sourceOnSide: boolean, targetOnSide: boolean) {
  const forward = source.lane.index < target.lane.index
  const portOffset = 5 + 2 * track
  const turnOffset = 9 + 3 * track
  const from = sourceOnSide
    ? { x: (source.start + source.end) / 2 + 3, y: source.crossStart }
    : { x: forward ? source.end : source.start, y: (source.crossStart + source.crossEnd) / 2 - portOffset }
  const to = targetOnSide
    ? { x: (target.start + target.end) / 2 - 3, y: target.crossStart - 1 }
    : { x: forward ? target.start - 1 : target.end + 1, y: (target.crossStart + target.crossEnd) / 2 - portOffset }
  const startTurn = sourceOnSide ? from.x : forward ? source.lane.end + turnOffset : source.lane.start - turnOffset
  const endTurn = targetOnSide ? to.x : forward ? target.lane.start - turnOffset : target.lane.end + turnOffset
  const trackY = source.lane.crossStart - wireGutterHeight + trackStart + track * trackSpacing
  const points = [from]
  if (!sourceOnSide) points.push({ x: startTurn, y: from.y })
  points.push({ x: startTurn, y: trackY }, { x: endTurn, y: trackY })
  if (!targetOnSide) points.push({ x: endTurn, y: to.y })
  points.push(to)
  return { points, label: { x: (startTurn + endTurn) / 2, y: trackY } }
}

export function layoutWires(
  edges: readonly VisibleCall[], boxes: ReadonlyMap<string, NodeBox>, direction: FlowDirection,
): Wire[] {
  const vertical = direction === 'vertical'
  const toCanvas = ({ x, y }: Point) => vertical ? { x: y, y: x } : { x, y }
  const wires: Wire[] = []
  const detours = []
  for (const edge of edges) {
    const source = boxes.get(edge.source.id)
    const target = boxes.get(edge.target.id)
    if (!source || !target) continue
    const start = Math.min(source.lane.index, target.lane.index)
    const end = Math.max(source.lane.index, target.lane.index)
    const sourceOnSide = vertical && edge.source.parent !== null
    const targetOnSide = vertical && edge.target.parent !== null
    if (end - start > 1 || (end > start && (sourceOnSide || targetOnSide))) {
      detours.push({ edge, source, target, start, end, sourceOnSide, targetOnSide })
      continue
    }

    const loop = edge.source === edge.target
    const points = vertical && start === end ? routeBesideLane(source, target, loop) : route(source, target, loop)
    const [from, first, second, to] = points
    const label = {
      x: (from.x + 3 * first.x + 3 * second.x + to.x) / 8,
      y: vertical ? (from.y + 3 * first.y + 3 * second.y + to.y) / 8 + 14 : (from.y + to.y) / 2 - 11,
    }
    wires.push({ edge, points: points.map(toCanvas), label: toCanvas(label), curved: true })
  }

  detours.sort((a, b) => a.start - b.start || a.end - b.end)
  const trackEnds = new Array<number>(trackCount).fill(-1)
  for (const { edge, source, target, start, end, sourceOnSide, targetOnSide } of detours) {
    // Reuse a free track first. Dense spans can share the track that clears soonest.
    const freeTrack = trackEnds.findIndex(endIndex => endIndex <= start)
    const track = freeTrack >= 0 ? freeTrack : trackEnds.indexOf(Math.min(...trackEnds))
    trackEnds[track] = Math.max(trackEnds[track], end)
    const { points, label } = routeThroughGutter(source, target, track, sourceOnSide, targetOnSide)
    wires.push({ edge, points: points.map(toCanvas), label: toCanvas(label), curved: false })
  }
  return wires
}

export function drawWires(
  context: CanvasRenderingContext2D,
  wires: readonly Wire[],
  view: { left: number; top: number; width: number; height: number },
  colors: WireColors,
  emphasized: ReadonlySet<VisibleCall> | null,
) {
  context.save()
  context.translate(-view.left, -view.top)
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.font = '600 11px Consolas, monospace'
  context.textAlign = 'center'
  context.textBaseline = 'middle'

  for (const { edge, points, label, curved } of wires) {
    if (points.every(point => point.x < view.left)
      || points.every(point => point.x > view.left + view.width)
      || points.every(point => point.y + 16 < view.top)
      || points.every(point => point.y - 16 > view.top + view.height)) continue

    const [start, first, second] = points
    const end = points[points.length - 1]
    const highlighted = emphasized?.has(edge) ?? false
    context.globalAlpha = emphasized && !highlighted ? 0.23 : 1
    context.strokeStyle = context.fillStyle = highlighted ? colors.activeStroke : colors.stroke
    context.lineWidth = highlighted ? 2.1 : 1.4
    context.beginPath()
    context.moveTo(start.x, start.y)
    if (curved) context.bezierCurveTo(first.x, first.y, second.x, second.y, end.x, end.y)
    else for (const point of points.slice(1)) context.lineTo(point.x, point.y)
    context.stroke()

    const previous = points[points.length - 2]
    const dx = end.x - previous.x
    const dy = end.y - previous.y
    const length = Math.hypot(dx, dy)
    const ux = dx / length
    const uy = dy / length
    const baseX = end.x - 7 * ux
    const baseY = end.y - 7 * uy
    context.beginPath()
    context.moveTo(end.x, end.y)
    context.lineTo(baseX + 4 * uy, baseY - 4 * ux)
    context.lineTo(baseX - 4 * uy, baseY + 4 * ux)
    context.closePath()
    context.fill()

    if (edge.count > 1 || edge.source.kind !== 'function' || edge.target.kind !== 'function') {
      const { x, y } = label
      const count = String(edge.count)
      const width = context.measureText(count).width + 10
      context.fillStyle = colors.labelBackground
      context.fillRect(x - width / 2, y - 7, width, 14)
      context.fillStyle = colors.labelText
      context.fillText(count, x, y)
    }
  }
  context.restore()
}
