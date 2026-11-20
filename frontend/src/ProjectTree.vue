<script setup lang="ts">
import type { ProjectDirectory } from './projectTree'

defineProps<{
  directory: ProjectDirectory
  activeFile: string
}>()

const emit = defineEmits<{ selectFile: [path: string] }>()
</script>

<template>
  <ul class="directory-contents" :class="{ 'directory-root': !directory.path }">
    <li v-for="child in directory.directories" :key="child.path">
      <details open class="directory-card">
        <summary>{{ child.name }}</summary>
        <ProjectTree :directory="child" :active-file="activeFile" @select-file="emit('selectFile', $event)" />
      </details>
    </li>
    <li v-for="file in directory.files" :key="file.path">
      <button
        type="button"
        class="project-file"
        :aria-current="file.path === activeFile ? 'true' : undefined"
        :title="file.path"
        @click="emit('selectFile', file.path)"
      >{{ file.name }}</button>
    </li>
  </ul>
</template>

<style scoped>
.directory-contents {
  display: grid;
  align-items: start;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.directory-root {
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 188px), 1fr));
  gap: 12px;
  padding: 3px;
  max-height: 400px;
  overflow: auto;
}

.directory-contents li { min-width: 0; }

.directory-card {
  padding: 8px;
  border: 1px solid #c5d5ed;
  border-radius: 11px;
  background: #edf3fc;
  overflow-wrap: anywhere;
}

.directory-card .directory-card {
  background: #f6f9ff;
}

.directory-card summary {
  padding: 2px 4px;
  color: #244270;
  font-size: .88rem;
  font-weight: 700;
}

.directory-card[open] > summary { margin-bottom: 6px; }
.directory-card:not([open]) > .directory-contents { display: none; }

.project-file {
  width: 100%;
  min-height: 34px;
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fff;
  color: inherit;
  font: .8rem/1.35 ui-monospace, monospace;
  text-align: left;
  overflow-wrap: anywhere;
}

.project-file:hover, .project-file[aria-current="true"] {
  border-color: #9fb9e8;
  background: #e5eeff;
  color: #1b4494;
}
</style>
