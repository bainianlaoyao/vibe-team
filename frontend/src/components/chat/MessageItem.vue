<script setup lang="ts">
import { computed } from 'vue';
import type { ChatMessage } from '@/types/chat';
import MarkdownBlock from './MarkdownBlock.vue';
import ToolCallBlock from './ToolCallBlock.vue';
import ThinkingBlock from './ThinkingBlock.vue';

const props = defineProps<{
  message: ChatMessage;
}>();

const isUser = computed(() => props.message.role === 'user');

const containerClass = computed(() => {
  return isUser.value
    ? 'flex flex-row-reverse mb-4 items-start gap-3'
    : 'flex flex-row mb-4 items-start gap-3';
});

const bubbleClass = computed(() => {
  return isUser.value
    ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[80%]'
    : 'bg-zinc-800 text-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[90%] w-full shadow-lg border border-zinc-700/50';
});
</script>

<template>
  <div :class="containerClass">
    <!-- Avatar -->
    <div
      class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold"
      :class="isUser ? 'bg-blue-500' : 'bg-purple-600'"
    >
      {{ isUser ? 'U' : 'C' }}
    </div>

    <!-- Message Content -->
    <div :class="bubbleClass">
      <div v-for="(part, index) in message.parts" :key="index" class="message-part">

        <!-- Text Content -->
        <MarkdownBlock
          v-if="part.type === 'text'"
          :content="part.content || ''"
        />

        <!-- Tool Invocation -->
        <ToolCallBlock
          v-else-if="part.type === 'tool-invocation' && part.toolInvocation"
          :tool="part.toolInvocation"
        />

        <!-- Thinking Process -->
        <ThinkingBlock
          v-else-if="part.type === 'thinking'"
          :content="part.content"
        />

      </div>
    </div>
  </div>
</template>
