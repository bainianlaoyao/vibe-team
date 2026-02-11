<script setup lang="ts">
import { computed } from 'vue';
import { useChatStore } from '@/stores/chat';

const store = useChatStore();
const pendingTool = computed(() => store.pendingTool);

function onApprove() {
  if (pendingTool.value) {
    store.approveTool(pendingTool.value.toolCallId);
  }
}

function onDeny() {
  if (pendingTool.value) {
    store.denyTool(pendingTool.value.toolCallId);
  }
}
</script>

<template>
  <div
    v-if="pendingTool"
    class="fixed inset-0 bg-bg-secondary/50 backdrop-blur-sm flex items-center justify-center z-50"
  >
    <div class="bg-bg-elevated/90 backdrop-blur-md border border-border rounded-lg shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200">

      <!-- Header -->
      <div class="bg-yellow-500/10 px-6 py-4 border-b border-yellow-500/20 flex items-center gap-3">
        <div class="text-yellow-600">⚠️</div>
        <h3 class="text-lg font-bold text-yellow-600">Tool Confirmation Required</h3>
      </div>

      <!-- Body -->
      <div class="p-6">
        <p class="text-text-secondary mb-4">
          The assistant requests to run the following command:
        </p>

        <div class="bg-bg-tertiary rounded-md p-4 mb-6 border border-border font-mono text-sm">
          <div class="text-green-600 font-bold mb-2">$ {{ pendingTool.toolName }}</div>
          <pre class="text-text-primary overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(pendingTool.args, null, 2) }}</pre>
        </div>

        <div class="text-xs text-text-tertiary italic text-center">
          Do you authorize this action?
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 bg-bg-tertiary flex gap-3 justify-end border-t border-border">
        <button
          @click="onDeny"
          class="px-4 py-2 rounded bg-bg-primary hover:bg-bg-secondary text-text-primary font-medium transition-colors border border-border"
        >
          Deny
        </button>
        <button
          @click="onApprove"
          class="px-4 py-2 rounded bg-green-600 hover:bg-green-500 text-white font-medium shadow-lg shadow-green-900/20 transition-all hover:scale-105"
        >
          Approve Execution
        </button>
      </div>
    </div>
  </div>
</template>
