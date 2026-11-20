<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import './analysis.css'

interface PythonSymbol {
  id: string
  name: string
  qualified_name: string
  file: string
  line: number
  end_line: number
  source: string
  source_truncated: boolean
}

interface Call {
  caller: string
  target: string | null
  expression: string
  line: number
  column: number
  status: 'resolved' | 'unresolved'
}

interface Analysis {
  root: string
  files: string[]
  symbols: PythonSymbol[]
  calls: Call[]
  warnings: string[]
}

const projectPath = ref('')
const analysis = ref<Analysis | null>(null)
const busy = ref(false)
const error = ref('')
const search = ref('')
const selectedId = ref('')
const highlightedLine = ref<number | null>(null)
const sourcePreview = ref<HTMLPreElement | null>(null)

const symbolIndex = computed(() => new Map(analysis.value?.symbols.map(symbol => [symbol.id, symbol])))
const selected = computed(() => symbolIndex.value.get(selectedId.value))
const visibleSymbols = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (analysis.value?.symbols ?? []).filter(symbol =>
    `${symbol.file} ${symbol.qualified_name}`.toLowerCase().includes(query),
  )
})
const outgoing = computed(() => (analysis.value?.calls ?? []).filter(call => call.caller === selectedId.value))
const incoming = computed(() => (analysis.value?.calls ?? []).filter(call => call.target === selectedId.value))
const unresolved = computed(() => outgoing.value.filter(call => call.status === 'unresolved'))
const resolvedCount = computed(() => analysis.value?.calls.filter(call => call.status === 'resolved').length ?? 0)
const sourceLines = computed(() => selected.value?.source.split('\n') ?? [])

function linkedSymbols(ids: Iterable<string | null>) {
  const symbols: PythonSymbol[] = []
  for (const id of new Set(ids)) {
    const symbol = id === null ? undefined : symbolIndex.value.get(id)
    if (symbol) symbols.push(symbol)
  }
  return symbols
}

const callers = computed(() => linkedSymbols(incoming.value.map(call => call.caller)))
const callees = computed(() => linkedSymbols(outgoing.value.map(call => call.target)))

function selectSymbol(id: string) {
  selectedId.value = id
  highlightedLine.value = null
  if (sourcePreview.value) sourcePreview.value.scrollTop = 0
}

async function revealLine(line: number) {
  highlightedLine.value = line
  await nextTick()
  sourcePreview.value?.querySelector('.highlighted')?.scrollIntoView({ block: 'nearest' })
}

async function scan() {
  const path = projectPath.value.trim()
  if (!path || busy.value) return

  busy.value = true
  error.value = ''
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : '扫描失败，请检查目录和后端服务。')
    }
    const result: Analysis = await response.json()
    analysis.value = result
    search.value = ''
    selectSymbol(result.calls.find(call => call.status === 'resolved')?.caller ?? result.symbols[0]?.id ?? '')
  } catch (cause) {
    error.value = cause instanceof TypeError
      ? '无法连接分析服务。请确认 FastAPI 后端已经启动。'
      : cause instanceof Error ? cause.message : '扫描失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <header class="topbar">
    <div class="brand"><span class="brand-icon" aria-hidden="true">⌘</span> CodeFlow</div>
    <span class="topbar-label">Python 调用分析</span>
  </header>

  <main class="workspace">
    <section class="project">
      <h1>项目调用图</h1>
      <form class="scan-form" @submit.prevent="scan">
        <label for="project-path">项目目录</label>
        <div class="scan-controls">
          <input
            id="project-path" v-model="projectPath" type="text" required maxlength="4096"
            placeholder="samples/python_basic" spellcheck="false"
          />
          <button type="submit" class="primary" :disabled="busy">{{ busy ? '扫描中…' : '扫描项目' }}</button>
        </div>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="analysis" role="status" class="summary">
        <span>{{ analysis.files.length }} 个 Python 文件</span>
        <span>{{ analysis.symbols.length }} 个函数和方法</span>
        <span>{{ resolvedCount }} 个已解析调用</span>
        <span>{{ analysis.calls.length - resolvedCount }} 个未解析调用</span>
      </p>
      <p v-else class="muted">输入后端所在机器上的目录路径，扫描其中的 Python 文件。</p>
      <details v-if="analysis?.warnings.length" class="warnings">
        <summary>{{ analysis.warnings.length }} 条扫描提示</summary>
        <ul><li v-for="(warning, index) in analysis.warnings" :key="index">{{ warning }}</li></ul>
      </details>
    </section>

    <div v-if="analysis?.symbols.length && selected" class="analysis-layout">
      <aside class="panel explorer" aria-label="函数列表">
        <h2>函数</h2>
        <input v-model="search" type="search" placeholder="搜索函数或文件" aria-label="搜索函数或文件" />
        <ul class="symbols">
          <li v-for="symbol in visibleSymbols" :key="symbol.id">
            <button :aria-pressed="symbol.id === selectedId" @click="selectSymbol(symbol.id)">
              <strong>{{ symbol.qualified_name }}</strong>
              <small>{{ symbol.file }}:{{ symbol.line }}</small>
            </button>
          </li>
        </ul>
        <p v-if="!visibleSymbols.length" class="muted">没有匹配的函数。</p>
      </aside>

      <div class="details">
        <section class="panel" aria-labelledby="graph-title">
          <h2 id="graph-title">直接调用关系</h2>
          <div class="graph">
            <div class="graph-column">
              <h3>调用者 <span>{{ callers.length }}</span></h3>
              <button v-for="symbol in callers" :key="symbol.id" class="node" @click="selectSymbol(symbol.id)">
                <strong>{{ symbol.qualified_name }}</strong>
                <small>{{ symbol.file }}:{{ symbol.line }}</small>
              </button>
              <p v-if="!callers.length" class="empty">暂无已解析调用者</p>
            </div>
            <span class="arrow" aria-hidden="true">→</span>
            <div class="graph-column">
              <h3>当前函数</h3>
              <div class="node focus">
                <strong>{{ selected.qualified_name }}</strong>
                <small>{{ selected.file }}:{{ selected.line }}</small>
              </div>
            </div>
            <span class="arrow" aria-hidden="true">→</span>
            <div class="graph-column">
              <h3>被调用者 <span>{{ callees.length }}</span></h3>
              <button v-for="symbol in callees" :key="symbol.id" class="node" @click="selectSymbol(symbol.id)">
                <strong>{{ symbol.qualified_name }}</strong>
                <small>{{ symbol.file }}:{{ symbol.line }}</small>
              </button>
              <p v-if="!callees.length" class="empty">暂无已解析被调用者</p>
            </div>
          </div>
          <details v-if="unresolved.length" class="unresolved">
            <summary>{{ unresolved.length }} 个未解析调用点</summary>
            <ul>
              <li v-for="(call, index) in unresolved" :key="index">
                <button
                  type="button"
                  :disabled="call.line >= selected.line + sourceLines.length"
                  @click="revealLine(call.line)"
                >
                  <code>{{ call.expression }}</code><span>第 {{ call.line }} 行</span>
                </button>
              </li>
            </ul>
          </details>
        </section>

        <section class="panel source" aria-labelledby="source-title">
          <div class="source-heading">
            <h2 id="source-title">源码</h2>
            <code>{{ selected.file }}:{{ selected.line }}–{{ selected.end_line }}</code>
          </div>
          <pre ref="sourcePreview" aria-label="函数源码"><code><span
            v-for="(line, index) in sourceLines" :key="index" class="source-line"
            :class="{ highlighted: selected.line + index === highlightedLine }"
          ><span class="line-number" aria-hidden="true">{{ selected.line + index }}</span><span>{{ line }}</span></span></code></pre>
          <p v-if="selected.source_truncated" class="muted">源码预览已截断。</p>
        </section>
      </div>
    </div>
    <div v-else-if="analysis" class="panel" role="status">目录中没有可展示的 Python 函数或方法。</div>
  </main>
</template>
