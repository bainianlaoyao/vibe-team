<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  content?: string;
}>();

const isOpen = ref(false);
</script>

<template>
  <div class="thinking-block my-2">
    <button
      @click="isOpen = !isOpen"
      class="flex items-center gap-2 text-xs font-mono text-gray-500 hover:text-gray-300 transition-colors cursor-pointer w-full text-left"
    >
      <span :class="{'rotate-90': isOpen, 'transition-transform duration-200': true}">▶</span>
      <span>Thinking Process...</span>
    </button>

    <div v-show="isOpen" class="mt-2 pl-4 border-l-2 border-gray-700 text-gray-400 text-sm font-mono whitespace-pre-wrap">
      {{ content }}
      <slot />
    </div>
  </div>
</template>
