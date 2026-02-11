<script setup lang="ts">
import { computed, ref } from 'vue';
import type { ToolInvocation } from '@/types/chat';

const props = defineProps<{
  tool: ToolInvocation;
}>();

const isExpanded = ref(false);

const stateColor = computed(() => {
  switch (props.tool.state) {
    case 'running': return 'text-yellow-500';
    case 'completed': return 'text-green-500';
    case 'failed': return 'text-red-500';
    case 'requires_action': return 'text-blue-400';
    default: return 'text-gray-500';
  }
});

const stateIcon = computed(() => {
  switch (props.tool.state) {
    case 'running': return '⏳';
    case 'completed': return '✓';
    case 'failed': return '✗';
    case 'requires_action': return '?';
    default: return '•';
  }
});
</script>

<template>
  <div class="tool-call-block my-2 rounded border border-border bg-bg-elevated overflow-hidden font-mono text-sm">
    <!-- Header -->
    <div
      class="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-bg-tertiary transition-colors"
      @click="isExpanded = !isExpanded"
    >
      <div class="flex items-center gap-2">
        <span :class="stateColor">{{ stateIcon }}</span>
        <span class="font-bold text-text-primary">{{ tool.toolName }}</span>
        <span class="text-text-tertiary text-xs truncate max-w-[200px]">
           {{ JSON.stringify(tool.args) }}
        </span>
      </div>
      <div class="text-xs text-text-muted">
        {{ tool.state }}
      </div>
    </div>

    <!-- Body (Expanded) -->
    <div v-if="isExpanded" class="px-3 py-2 border-t border-border bg-bg-tertiary/50">
      <div class="mb-2">
        <div class="text-xs text-text-tertiary mb-1">Arguments:</div>
        <pre class="text-xs text-text-secondary overflow-x-auto p-2 bg-bg-secondary rounded">{{ JSON.stringify(tool.args, null, 2) }}</pre>
      </div>

      <div v-if="tool.result">
        <div class="text-xs text-text-tertiary mb-1">Result:</div>
        <pre class="text-xs text-green-600 overflow-x-auto p-2 bg-bg-secondary rounded max-h-60">{{ tool.result }}</pre>
      </div>
    </div>
  </div>
</template>
