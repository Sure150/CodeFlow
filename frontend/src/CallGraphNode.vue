<script setup lang="ts">
import type { GraphNode } from './callGraph'

defineProps<{
  node: GraphNode
  expanded: ReadonlySet<string>
  internalCounts: ReadonlyMap<string, number>
  selectedId: string
  mutedNodes: ReadonlySet<string>
}>()

const emit = defineEmits<{ toggle: [id: string]; select: [id: string] }>()
const kindLabel = { directory: '目录', file: '文件', class: '类', function: '函数' }
</script>

<template>
  <div class="graph-branch" :class="[`branch-${node.kind}`, { 'branch-open': expanded.has(node.id) }]">
    <button
      v-if="node.symbol"
      type="button"
      class="graph-node function-node"
      :class="{ 'graph-node-muted': mutedNodes.has(node.id) }"
      :data-graph-node="node.id"
      :title="`${node.symbol.qualified_name} · ${node.path}:${node.symbol.line}`"
      :aria-pressed="selectedId === node.symbol.id"
      @click="emit('select', node.symbol.id)"
    >
      <span class="graph-node-name">{{ node.name }}()</span>
      <span class="function-location">{{ node.path.split('/').at(-1) }}:{{ node.symbol.line }}</span>
    </button>
    <button
      v-else
      type="button"
      class="graph-node container-node"
      :class="{ 'graph-node-muted': mutedNodes.has(node.id) }"
      :data-graph-node="node.id"
      :title="`${kindLabel[node.kind]} · ${node.kind === 'class' ? node.name : node.path}`"
      :aria-expanded="expanded.has(node.id)"
      @click="emit('toggle', node.id)"
    >
      <span class="graph-caret" aria-hidden="true"></span>
      <span class="graph-node-name">{{ node.name }}{{ node.kind === 'directory' ? '/' : '' }}</span>
      <span v-if="internalCounts.has(node.id)" class="internal-count">
        {{ internalCounts.get(node.id) }} 个内部调用
      </span>
      <span v-else class="graph-node-kind">{{ kindLabel[node.kind] }}</span>
    </button>
    <div v-if="node.children.length && expanded.has(node.id)" class="graph-children">
      <CallGraphNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :expanded="expanded"
        :internal-counts="internalCounts"
        :selected-id="selectedId"
        :muted-nodes="mutedNodes"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.graph-branch {
  --node-tone: var(--graph-tone, var(--accent));
  min-width: 0;
}
.branch-open {
  border: 1px solid color-mix(in srgb, var(--node-tone), var(--line) 55%);
  border-radius: 9px;
  background: color-mix(in srgb, var(--node-tone) 5%, var(--surface));
}
.branch-file.branch-open, .branch-class.branch-open { border-color: var(--line-strong); }
.graph-children { display: grid; gap: 9px; padding: 10px; }
.graph-node {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  padding: 8px 10px;
  color: var(--text);
  text-align: left;
  border: 1px solid var(--line-strong);
  border-radius: 7px;
  background: var(--surface);
}
.graph-node-muted { opacity: .48; }
.graph-node:hover, .graph-node:focus-visible, .graph-node[aria-pressed="true"] {
  opacity: 1;
  border-color: var(--line-accent);
  background: var(--surface-active);
  color: var(--accent);
}
.branch-directory.branch-open {
  min-height: 120px;
  border-radius: 11px;
}
.branch-directory > .container-node {
  height: 48px;
  border-color: color-mix(in srgb, var(--node-tone), var(--line) 55%);
  border-radius: 11px;
  background: color-mix(in srgb, var(--node-tone) 13%, var(--surface));
  color: var(--node-tone);
}
.branch-directory > .container-node:hover { background: color-mix(in srgb, var(--node-tone) 20%, var(--surface)); }
.branch-open > .container-node { border: 0; border-bottom: 1px solid var(--line); border-radius: 8px 8px 0 0; }
.branch-directory.branch-open > .container-node { border-radius: 10px 10px 0 0; }
.graph-node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 650 .8rem/1.35 var(--font-code);
}
.graph-node-kind, .internal-count {
  flex: none;
  color: var(--muted);
  font-size: .68rem;
  white-space: nowrap;
}
.internal-count { color: var(--node-tone); font-variant-numeric: tabular-nums; }
.graph-caret {
  flex: none;
  width: 6px;
  height: 6px;
  margin-right: 2px;
  border: solid currentColor;
  border-width: 0 1px 1px 0;
  transform: rotate(-45deg);
}
.graph-node[aria-expanded="true"] .graph-caret { transform: translateY(-2px) rotate(45deg); }
.function-node {
  display: grid;
  gap: 3px;
  min-height: 54px;
  border-inline-start: 3px solid var(--node-tone);
}
.function-node[aria-pressed="true"] { border-color: var(--accent); }
.function-location {
  overflow: hidden;
  color: var(--muted);
  text-overflow: ellipsis;
  white-space: nowrap;
  font: .69rem/1.35 var(--font-code);
}
</style>
