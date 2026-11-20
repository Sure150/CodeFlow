<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import ProjectTree from './ProjectTree.vue'
import { buildProjectTree } from './projectTree'
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
const picking = ref(false)
const error = ref('')
const search = ref('')
const fileFilter = ref<string | null>(null)
const selectedId = ref('')
const highlightedLine = ref<number | null>(null)
const sourcePreview = ref<HTMLPreElement | null>(null)

const symbolIndex = computed(() => new Map(analysis.value?.symbols.map(symbol => [symbol.id, symbol])))
const selected = computed(() => symbolIndex.value.get(selectedId.value))
const projectTree = computed(() => buildProjectTree(analysis.value?.files ?? []))
const activeFile = computed(() => fileFilter.value ?? selected.value?.file ?? '')
const visibleSymbols = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (analysis.value?.symbols ?? []).filter(symbol =>
    (!fileFilter.value || symbol.file === fileFilter.value)
    && `${symbol.file} ${symbol.qualified_name}`.toLowerCase().includes(query),
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
  const symbol = symbolIndex.value.get(id)
  if (fileFilter.value && symbol && symbol.file !== fileFilter.value) {
    fileFilter.value = symbol.file
    search.value = ''
  }
  selectedId.value = id
  highlightedLine.value = null
  if (sourcePreview.value) sourcePreview.value.scrollTop = 0
}

function selectFile(path: string) {
  fileFilter.value = path
  search.value = ''
  selectSymbol(analysis.value?.symbols.find(symbol => symbol.file === path)?.id ?? '')
}

async function revealLine(line: number) {
  highlightedLine.value = line
  await nextTick()
  sourcePreview.value?.querySelector('.highlighted')?.scrollIntoView({ block: 'nearest' })
}

async function chooseDirectory() {
  if (picking.value || busy.value) return

  picking.value = true
  error.value = ''
  try {
    const response = await fetch('/api/choose-directory', { method: 'POST' })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(typeof body?.detail === 'string' ? body.detail : '无法打开文件夹选择窗口。')
    }
    const result: { path: string | null } = await response.json()
    if (result.path) projectPath.value = result.path
  } catch (cause) {
    error.value = cause instanceof TypeError
      ? '无法连接分析服务。请确认 FastAPI 后端已经启动。'
      : cause instanceof Error ? cause.message : '选择文件夹失败'
  } finally {
    picking.value = false
  }
}

async function scan() {
  const path = projectPath.value.trim()
  if (!path || busy.value || picking.value) return

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
    fileFilter.value = null
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
  </header>

  <main class="workspace">
    <section class="project">
      <h1>项目调用图</h1>
      <form class="scan-form" @submit.prevent="scan">
        <label for="project-path">项目目录</label>
        <div class="scan-controls">
          <input
            id="project-path" v-model="projectPath" type="text" required maxlength="4096"
            placeholder="samples/python_basic" spellcheck="false" :readonly="picking"
          />
          <button type="button" class="secondary" :disabled="busy || picking" @click="chooseDirectory">
            {{ picking ? '等待选择…' : '选择文件夹' }}
          </button>
          <button type="submit" class="primary" :disabled="busy || picking">
            {{ busy ? '扫描中…' : '扫描项目' }}
          </button>
        </div>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="analysis" role="status" class="summary">
        <span>{{ analysis.files.length }} 个 Python 文件</span>
        <span>{{ analysis.symbols.length }} 个函数和方法</span>
        <span>{{ resolvedCount }} 个已解析调用</span>
        <span>{{ analysis.calls.length - resolvedCount }} 个未解析调用</span>
      </p>
      <details v-if="analysis?.warnings.length" class="warnings">
        <summary>{{ analysis.warnings.length }} 条扫描提示</summary>
        <ul><li v-for="(warning, index) in analysis.warnings" :key="index">{{ warning }}</li></ul>
      </details>
    </section>

    <section v-if="analysis?.files.length" class="panel project-structure" aria-labelledby="structure-title">
      <h2 id="structure-title">项目结构</h2>
      <ProjectTree
        :key="analysis.root"
        :directory="projectTree"
        :active-file="activeFile"
        @select-file="selectFile"
      />
    </section>

    <div v-if="analysis?.files.length" class="analysis-layout">
      <aside class="panel explorer" aria-label="函数列表">
        <div class="explorer-heading">
          <h2>函数</h2>
          <button v-if="fileFilter" class="all-files" type="button" @click="fileFilter = null">全部文件</button>
        </div>
        <p v-if="fileFilter" class="file-filter">{{ fileFilter }}</p>
        <input v-model="search" type="search" placeholder="搜索函数或文件" aria-label="搜索函数或文件" />
        <ul class="symbols">
          <li v-for="symbol in visibleSymbols" :key="symbol.id">
            <button :aria-pressed="symbol.id === selectedId" @click="selectSymbol(symbol.id)">
              <strong>{{ symbol.qualified_name }}</strong>
              <small>{{ symbol.file }}:{{ symbol.line }}</small>
            </button>
          </li>
        </ul>
        <p v-if="!visibleSymbols.length" class="muted">
          {{ search ? '没有匹配的函数。' : '没有可展示的函数或方法。' }}
        </p>
      </aside>

      <div v-if="selected" class="details">
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
      <div v-else class="panel graph-empty" role="status">
        {{ fileFilter ? '请从项目结构中选择其他文件。' : '选择函数后可查看调用关系和源码。' }}
      </div>
    </div>
    <div v-else-if="analysis" class="panel" role="status">目录中没有可展示的 Python 文件。</div>
  </main>
</template>
