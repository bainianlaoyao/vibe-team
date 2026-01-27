<script setup lang="ts">
import { computed } from 'vue'
import type { Agent } from '../types/demo'

const props = defineProps<{
  agent: Agent
}>()

const statusColor = computed(() => {
  const colors = {
    idle: 'bg-white/20',
    thinking: 'bg-holographic-blue animate-pulse',
    coding: 'bg-neon-green',
    blocked: 'bg-cyber-yellow animate-pulse',
    done: 'bg-neon-green',
    error: 'bg-signal-red animate-pulse'
  }
  return colors[props.agent.status]
})

const roleIcon = computed(() => {
  const icons = {
    backend: '⚙️',
    frontend: '🎨',
    design: '✨',
    architect: '🏗️'
  }
  return icons[props.agent.role]
})
</script>

<template>
  <div class="glass rounded-xl p-4 border border-white/5 hover:border-white/10 transition-all duration-300">
    <div class="flex items-start gap-3">
      <!-- Avatar -->
      <div class="relative">
        <div class="w-12 h-12 rounded-lg bg-gradient-to-br from-white/10 to-white/5 flex items-center justify-center text-2xl">
          {{ roleIcon }}
        </div>
        <div :class="[statusColor, 'absolute -top-1 -right-1 w-4 h-4 rounded-full border-2 border-glass-panel']"></div>
      </div>

      <!-- Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center justify-between mb-1">
          <h4 class="font-semibold text-white">{{ agent.name }}</h4>
          <span class="text-xs text-white/40 capitalize">{{ agent.role }}</span>
        </div>

        <!-- Current Action -->
        <p class="text-sm text-white/60 font-mono truncate mb-2">
          {{ agent.currentAction }}
        </p>

        <!-- Artifacts -->
        <div v-if="agent.artifacts.length > 0" class="flex flex-wrap gap-1">
          <span
            v-for="artifact in agent.artifacts.slice(-3)"
            :key="artifact.path"
            class="text-xs px-2 py-1 bg-white/5 rounded text-white/40 font-mono truncate max-w-[120px]"
            :title="artifact.path"
          >
            {{ artifact.name }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
