export interface PythonSymbol {
  id: string
  name: string
  qualified_name: string
  file: string
  line: number
  end_line: number
  source: string
  source_truncated: boolean
  class_id?: string | null
}

interface PythonClass {
  id: string
  name: string
  file: string
  parent_id: string | null
}

export interface Call {
  caller: string
  target: string | null
  expression: string
  line: number
  column: number
  status: 'resolved' | 'unresolved'
}

export interface Analysis {
  root: string
  files: string[]
  symbols: PythonSymbol[]
  calls: Call[]
  warnings: string[]
  classes?: PythonClass[]
}

type ResolvedCall = Call & { target: string }

export interface GraphNode {
  id: string
  kind: 'directory' | 'file' | 'class' | 'function'
  name: string
  path: string
  parent: GraphNode | null
  children: GraphNode[]
  symbol?: PythonSymbol
}

export interface CallGraph {
  roots: GraphNode[]
  symbols: Map<string, PythonSymbol>
  functions: Map<string, GraphNode>
  calls: ResolvedCall[]
}

export interface VisibleCall {
  source: GraphNode
  target: GraphNode
  count: number
  selected: boolean
}

export function buildCallGraph(analysis: Analysis): CallGraph {
  const allSymbols = new Map(analysis.symbols.map(symbol => [symbol.id, symbol]))
  const classes = new Map((analysis.classes ?? []).map(item => [item.id, item]))
  const calls = analysis.calls.filter((call): call is ResolvedCall =>
    call.status === 'resolved' && call.target !== null
    && allSymbols.has(call.caller) && allSymbols.has(call.target),
  )
  const relatedIds = new Set<string>()
  for (const call of calls) {
    relatedIds.add(call.caller)
    relatedIds.add(call.target)
  }

  const roots: GraphNode[] = []
  const containers = new Map<string, GraphNode>()
  const symbols = new Map<string, PythonSymbol>()
  const functions = new Map<string, GraphNode>()

  function addContainer(kind: 'directory' | 'file' | 'class', key: string, name: string,
                        path: string, parent: GraphNode | null): GraphNode {
    const id = `${kind}:${key}`
    const existing = containers.get(id)
    if (existing) return existing
    const node: GraphNode = { id, kind, name, path, parent, children: [] }
    containers.set(id, node)
    const siblings = parent?.children ?? roots
    siblings.push(node)
    return node
  }

  function fileContainer(file: string): GraphNode {
    const existing = containers.get(`file:${file}`)
    if (existing) return existing
    const parts = file.split('/')
    const filename = parts.pop() ?? file
    let parent: GraphNode | null = null
    let path = ''
    for (const part of parts) {
      path = path ? `${path}/${part}` : part
      parent = addContainer('directory', path, part, path, parent)
    }
    return addContainer('file', file, filename, file, parent)
  }

  function classContainer(classId: string, file: GraphNode): GraphNode {
    const item = classes.get(classId)
    if (!item || item.file !== file.path) return file
    const existing = containers.get(`class:${classId}`)
    if (existing) return existing
    const parent = item.parent_id ? classContainer(item.parent_id, file) : file
    return addContainer('class', classId, item.name, file.path, parent)
  }

  for (const id of relatedIds) {
    const symbol = allSymbols.get(id)!
    const file = fileContainer(symbol.file)
    const parent = symbol.class_id ? classContainer(symbol.class_id, file) : file
    const node: GraphNode = {
      id: `function:${id}`, kind: 'function', name: symbol.name,
      path: symbol.file, parent, children: [], symbol,
    }
    parent.children.push(node)
    symbols.set(id, symbol)
    functions.set(id, node)
  }

  return { roots, symbols, functions, calls }
}

export function rootOf(node: GraphNode): GraphNode {
  let root = node
  while (root.parent) root = root.parent
  return root
}

export function orderGraphRoots(graph: CallGraph): GraphNode[] {
  const rootsByFunction = new Map<string, GraphNode>()
  for (const [id, node] of graph.functions) {
    rootsByFunction.set(id, rootOf(node))
  }

  const successors = new Map(graph.roots.map(root => [root, new Set<GraphNode>()]))
  const incoming = new Map(graph.roots.map(root => [root, 0]))
  for (const call of graph.calls) {
    const source = rootsByFunction.get(call.caller)!
    const target = rootsByFunction.get(call.target)!
    const targets = successors.get(source)!
    if (source !== target && !targets.has(target)) {
      targets.add(target)
      incoming.set(target, incoming.get(target)! + 1)
    }
  }

  const columns: GraphNode[] = []
  const remaining = new Set(graph.roots)
  const ready = graph.roots.filter(root => incoming.get(root) === 0)
  while (remaining.size) {
    // A cycle can leave no root with zero incoming edges. Start at its first remaining root.
    const root = ready.shift() ?? remaining.values().next().value!
    remaining.delete(root)
    columns.push(root)
    for (const target of successors.get(root)!) {
      if (!remaining.has(target)) continue
      const count = incoming.get(target)! - 1
      incoming.set(target, count)
      if (count === 0) ready.push(target)
    }
  }
  return columns
}

export function projectCalls(graph: CallGraph, expanded: ReadonlySet<string>, selectedId = '') {
  const endpoints = new Map<string, GraphNode>()

  function visit(node: GraphNode, collapsedParent?: GraphNode) {
    if (node.symbol) {
      endpoints.set(node.symbol.id, collapsedParent ?? node)
      return
    }
    const collapsed = collapsedParent ?? (expanded.has(node.id) ? undefined : node)
    for (const child of node.children) visit(child, collapsed)
  }

  for (const root of graph.roots) visit(root)

  const edges = new Map<string, VisibleCall>()
  const internalCounts = new Map<string, number>()
  for (const call of graph.calls) {
    const source = endpoints.get(call.caller)!
    const target = endpoints.get(call.target)!
    if (source === target && source.kind !== 'function') {
      internalCounts.set(source.id, (internalCounts.get(source.id) ?? 0) + 1)
      continue
    }
    const key = JSON.stringify([source.id, target.id])
    const edge = edges.get(key)
    const selected = call.caller === selectedId || call.target === selectedId
    if (edge) {
      edge.count += 1
      edge.selected ||= selected
    } else edges.set(key, { source, target, count: 1, selected })
  }

  return { edges: [...edges.values()], internalCounts }
}
