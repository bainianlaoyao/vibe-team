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
    class="fixed inset-0 bg-black/80 flex items-center justify-center z-50 backdrop-blur-sm"
  >
    <div class="bg-zinc-900 border border-yellow-600/50 rounded-lg shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in duration-200">

      <!-- Header -->
      <div class="bg-yellow-900/20 px-6 py-4 border-b border-yellow-600/20 flex items-center gap-3">
        <div class="text-yellow-500">⚠️</div>
        <h3 class="text-lg font-bold text-yellow-500">Tool Confirmation Required</h3>
      </div>

      <!-- Body -->
      <div class="p-6">
        <p class="text-gray-300 mb-4">
          The assistant requests to run the following command:
        </p>

        <div class="bg-black rounded-md p-4 mb-6 border border-zinc-800 font-mono text-sm">
          <div class="text-green-400 font-bold mb-2">$ {{ pendingTool.toolName }}</div>
          <pre class="text-gray-400 overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(pendingTool.args, null, 2) }}</pre>
        </div>

        <div class="text-xs text-gray-500 italic text-center">
          Do you authorize this action?
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 bg-zinc-950 flex gap-3 justify-end border-t border-zinc-800">
        <button
          @click="onDeny"
          class="px-4 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-gray-300 font-medium transition-colors border border-zinc-700"
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
