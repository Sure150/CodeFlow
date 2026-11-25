<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import CallGraph from './CallGraph.vue'
import { buildCallGraph, orderGraphRoots, rootOf, type Analysis, type PythonSymbol } from './callGraph'
import './analysis.css'

type ColorScheme = 'light' | 'dark'
type ThemePreference = ColorScheme | 'system'

const themeKey = 'codeflow-theme'
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)')
const systemScheme = ref<ColorScheme>(systemTheme.matches ? 'dark' : 'light')
const theme = ref<ThemePreference>(readTheme())
const colorScheme = computed(() => theme.value === 'system' ? systemScheme.value : theme.value)

function readTheme(): ThemePreference {
  try {
    const saved = window.localStorage.getItem(themeKey)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // The browser can block access to local storage.
  }
  return 'system'
}

function updateSystemTheme(event: MediaQueryListEvent) {
  systemScheme.value = event.matches ? 'dark' : 'light'
}

watch(colorScheme, scheme => {
  document.documentElement.dataset.theme = scheme
}, { immediate: true, flush: 'sync' })

watch(theme, preference => {
  try {
    window.localStorage.setItem(themeKey, preference)
  } catch {
    // The theme still applies to the current page.
  }
})

onMounted(() => systemTheme.addEventListener('change', updateSystemTheme))
onBeforeUnmount(() => systemTheme.removeEventListener('change', updateSystemTheme))

const projectPath = ref('')
const analysis = ref<Analysis | null>(null)
const busy = ref(false)
const picking = ref(false)
const error = ref('')
const search = ref('')
const rootFilter = ref('')
const selectedId = ref('')
const drawer = ref<'navigator' | 'inspector' | null>(null)
const navigatorToggle = ref<HTMLButtonElement | null>(null)
const inspectorToggle = ref<HTMLButtonElement | null>(null)
const functionSearch = ref<HTMLInputElement | null>(null)
const highlightedLine = ref<number | null>(null)
const sourcePreview = ref<HTMLPreElement | null>(null)
const graphView = ref<InstanceType<typeof CallGraph> | null>(null)

const graph = computed(() => analysis.value ? buildCallGraph(analysis.value) : null)
const hasGraph = computed(() => Boolean(graph.value?.roots.length))
const roots = computed(() => graph.value ? orderGraphRoots(graph.value) : [])
const selected = computed(() => graph.value?.symbols.get(selectedId.value))
const query = computed(() => search.value.trim().toLowerCase())
const functionIndex = computed(() => [...(graph.value?.functions.values() ?? [])].map(node => ({
  symbol: node.symbol!, rootId: rootOf(node).id,
})))
const rootCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const { rootId } of functionIndex.value) counts.set(rootId, (counts.get(rootId) ?? 0) + 1)
  return counts
})
const searchResults = computed(() => functionIndex.value.filter(({ symbol, rootId }) =>
  (!rootFilter.value || rootId === rootFilter.value)
  && `${symbol.file} ${symbol.qualified_name}`.toLowerCase().includes(query.value),
).map(({ symbol }) => symbol))
const outgoing = computed(() => graph.value?.calls.filter(call => call.caller === selectedId.value) ?? [])
const incoming = computed(() => graph.value?.calls.filter(call => call.target === selectedId.value) ?? [])
const unresolved = computed(() => (analysis.value?.calls ?? []).filter(call =>
  call.caller === selectedId.value && call.status === 'unresolved',
))
const resolvedCount = computed(() => graph.value?.calls.length ?? 0)
const sourceLines = computed(() => selected.value?.source.split('\n') ?? [])

function linkedSymbols(ids: Iterable<string>) {
  const symbols: PythonSymbol[] = []
  for (const id of new Set(ids)) {
    const symbol = graph.value?.symbols.get(id)
    if (symbol) symbols.push(symbol)
  }
  return symbols
}

const callers = computed(() => linkedSymbols(incoming.value.map(call => call.caller)))
const callees = computed(() => linkedSymbols(outgoing.value.map(call => call.target)))

function selectSymbol(id: string) {
  const node = graph.value?.functions.get(id)
  if (rootFilter.value && node) rootFilter.value = rootOf(node).id
  selectedId.value = id
  drawer.value = 'inspector'
  highlightedLine.value = null
  if (sourcePreview.value) sourcePreview.value.scrollTop = 0
  void graphView.value?.revealFunction(id)
}

function closeDrawer() {
  if (!drawer.value) return
  const toggle = drawer.value === 'navigator' ? navigatorToggle : inspectorToggle
  drawer.value = null
  void nextTick(() => toggle.value?.focus())
}

function toggleDrawer(panel: 'navigator' | 'inspector') {
  if (drawer.value === panel) {
    closeDrawer()
    return
  }
  drawer.value = panel
  if (panel === 'navigator') void nextTick(() => functionSearch.value?.focus())
}

function clearSelection() {
  selectedId.value = ''
  highlightedLine.value = null
}

function clearGraphSelection() {
  clearSelection()
  if (drawer.value === 'inspector') drawer.value = null
}

function selectRoot(id: string) {
  rootFilter.value = id
  const node = graph.value?.functions.get(selectedId.value)
  if (node && id && rootOf(node).id !== id) clearSelection()
  if (id) graphView.value?.revealRoot(id)
}

function selectSearchResult() {
  if (searchResults.value.length) selectSymbol(searchResults.value[0].id)
}

async function revealLine(line: number) {
  const source = sourcePreview.value?.closest('details')
  if (source) source.open = true
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
    rootFilter.value = ''
    clearSelection()
    drawer.value = null
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
  <header class="topbar" :class="{ 'topbar--graph': hasGraph }">
    <div class="brand"><span class="brand-icon" aria-hidden="true">⌘</span> CodeFlow</div>
    <div v-show="hasGraph" id="workbench-scan" class="workbench-scan"></div>
    <div class="topbar-actions">
      <details v-show="hasGraph" class="scan-report">
        <summary>扫描结果</summary>
        <div id="workbench-report" class="scan-report-content"></div>
      </details>
      <label class="theme-control">
        <span>主题</span>
        <select v-model="theme" aria-label="主题">
          <option value="system">跟随系统</option>
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select>
      </label>
    </div>
  </header>

  <main class="workspace" :class="{ 'workspace--graph': hasGraph }" @keydown.esc="closeDrawer">
    <section v-show="!hasGraph" class="project">
      <h1>扫描项目调用关系</h1>
      <Teleport to="#workbench-scan" :disabled="!hasGraph">
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
      </Teleport>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <Teleport to="#workbench-report" :disabled="!hasGraph">
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
      </Teleport>
    </section>

    <div v-if="graph?.roots.length" class="graph-workspace">
      <p v-if="error" class="error graph-scan-error" role="alert">{{ error }}</p>
      <aside v-show="drawer === 'navigator'" id="graph-navigator" class="panel graph-navigator" aria-labelledby="navigator-title">
        <div class="inspector-heading">
          <h2 id="navigator-title">目录索引</h2>
          <button type="button" class="inspector-clear" @click="closeDrawer">关闭</button>
        </div>
        <form class="navigator-search" role="search" @submit.prevent="selectSearchResult">
          <label for="function-search">搜索函数或路径</label>
          <input id="function-search" ref="functionSearch" v-model="search" type="search" />
        </form>
        <section class="navigator-section" aria-labelledby="root-filters-title">
          <h3 id="root-filters-title">目录和文件</h3>
          <ul class="navigator-roots">
            <li>
              <button type="button" class="navigator-option" :aria-pressed="!rootFilter" @click="selectRoot('')">
                <span class="navigator-label">全部</span>
                <span class="navigator-count">{{ functionIndex.length }}</span>
              </button>
            </li>
            <li v-for="(node, index) in roots" :key="node.id">
              <button
                type="button"
                class="navigator-option"
                :data-graph-tone="index % 5"
                :aria-pressed="rootFilter === node.id"
                :title="node.path"
                @click="selectRoot(node.id)"
              >
                <span class="navigator-dot" aria-hidden="true"></span>
                <span class="navigator-label">{{ node.name }}{{ node.kind === 'directory' ? '/' : '' }}</span>
                <span class="navigator-count" :aria-label="`${rootCounts.get(node.id)} 个函数`">{{ rootCounts.get(node.id) }}</span>
              </button>
            </li>
          </ul>
        </section>
        <section class="navigator-section" aria-labelledby="function-index-title">
          <h3 id="function-index-title">函数索引</h3>
          <ul class="navigator-functions">
            <li v-for="symbol in searchResults" :key="symbol.id">
              <button
                type="button"
                class="navigator-function"
                :aria-pressed="selectedId === symbol.id"
                :title="`${symbol.qualified_name} · ${symbol.file}:${symbol.line}`"
                @click="selectSymbol(symbol.id)"
              >
                <strong>{{ symbol.qualified_name }}</strong>
                <small>{{ symbol.file }}:{{ symbol.line }}</small>
              </button>
            </li>
          </ul>
          <p v-if="!searchResults.length" class="navigator-empty">未找到匹配的函数。</p>
        </section>
      </aside>

      <CallGraph
        ref="graphView"
        :graph="graph"
        :roots="roots"
        :root-filter="rootFilter"
        :selected-id="selectedId"
        :color-scheme="colorScheme"
        @select="selectSymbol"
        @clear="clearGraphSelection"
      >
        <template #actions>
          <button
            ref="navigatorToggle" type="button" class="secondary drawer-toggle"
            :aria-expanded="drawer === 'navigator'" aria-controls="graph-navigator" @click="toggleDrawer('navigator')"
          >目录索引</button>
          <button
            ref="inspectorToggle" type="button" class="secondary drawer-toggle"
            :aria-expanded="drawer === 'inspector'" aria-controls="graph-inspector" @click="toggleDrawer('inspector')"
          >调用详情</button>
        </template>
      </CallGraph>

      <aside v-show="drawer === 'inspector'" id="graph-inspector" class="panel graph-inspector" aria-labelledby="inspector-title">
        <div class="inspector-heading">
          <h2 id="inspector-title">调用详情</h2>
          <div class="inspector-actions">
            <button v-if="selected" type="button" class="inspector-clear" @click="clearSelection">清除选中</button>
            <button type="button" class="inspector-clear" @click="closeDrawer">关闭</button>
          </div>
        </div>
        <template v-if="selected">
          <div class="inspector-symbol">
            <strong>{{ selected.qualified_name }}</strong>
            <code>{{ selected.file }}:{{ selected.line }}–{{ selected.end_line }}</code>
          </div>
          <section v-for="group in [{ name: '调用者', symbols: callers }, { name: '被调用者', symbols: callees }]"
            :key="group.name" class="inspector-related">
            <h3>{{ group.name }} <span>{{ group.symbols.length }}</span></h3>
            <ul v-if="group.symbols.length" class="inspector-links">
              <li v-for="symbol in group.symbols" :key="symbol.id">
                <button type="button" @click="selectSymbol(symbol.id)">
                  <strong>{{ symbol.qualified_name }}</strong>
                  <small>{{ symbol.file }}:{{ symbol.line }}</small>
                </button>
              </li>
            </ul>
            <p v-else class="navigator-empty">暂无已解析{{ group.name }}</p>
          </section>
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
          <details class="inspector-source" open>
            <summary>源码</summary>
            <pre ref="sourcePreview" aria-label="函数源码"><code><span
              v-for="(line, index) in sourceLines" :key="index" class="source-line"
              :class="{ highlighted: selected.line + index === highlightedLine }"
            ><span class="line-number" aria-hidden="true">{{ selected.line + index }}</span><span>{{ line }}</span></span></code></pre>
            <p v-if="selected.source_truncated" class="muted">源码预览已截断。</p>
          </details>
        </template>
        <p v-else class="navigator-empty">选择一个函数查看调用关系和源码。</p>
      </aside>
    </div>
    <div v-else-if="analysis" class="panel graph-empty" role="status">
      {{ analysis.files.length ? '没有找到可解析的项目内调用关系。' : '目录中没有可展示的 Python 文件。' }}
    </div>
  </main>
</template>
