<script setup lang="ts">
import { onMounted, ref } from 'vue'

const connection = ref('正在连接分析服务…')

async function checkConnection() {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) {
      throw new Error('Health check failed')
    }

    const health: { status?: string } = await response.json()
    connection.value = health.status === 'ok' ? '分析服务已连接' : '分析服务状态异常'
  } catch {
    connection.value = '无法连接分析服务'
  }
}

onMounted(checkConnection)
</script>

<template>
  <main>
    <h1>CodeFlow</h1>
    <p role="status">{{ connection }}</p>
  </main>
</template>

<style>
:root {
  font-family: system-ui, sans-serif;
  color-scheme: light dark;
}

main {
  max-width: 48rem;
  margin: 4rem auto;
  padding: 0 1.5rem;
}
</style>
