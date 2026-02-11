<script setup lang="ts">
import { computed } from 'vue';
import type { ChatMessage } from '@/types/chat';
import MarkdownBlock from './MarkdownBlock.vue';
import ToolCallBlock from './ToolCallBlock.vue';
import ThinkingBlock from './ThinkingBlock.vue';
import InputRequestBlock from './InputRequestBlock.vue';

const props = defineProps<{
  message: ChatMessage;
}>();

const emit = defineEmits<{
  (e: 'submit-input', payload: { questionId: string; answer: string }): void;
}>();

const isUser = computed(() => props.message.role === 'user');
const isSystem = computed(() => props.message.role === 'system');

const containerClass = computed(() => {
  if (isSystem.value) {
    return 'mb-4';
  }
  return isUser.value
    ? 'flex flex-row-reverse mb-4 items-start gap-3'
    : 'flex flex-row mb-4 items-start gap-3';
});

const bubbleClass = computed(() => {
  if (isSystem.value) {
    return 'bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-amber-900 max-w-[95%]';
  }
  return isUser.value
    ? 'bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[80%]'
    : 'bg-bg-elevated text-text-primary rounded-2xl rounded-tl-sm px-4 py-3 max-w-[90%] w-full shadow-lg border border-border';
});
</script>

<template>
  <div :class="containerClass">
    <!-- Avatar -->
    <div
      v-if="!isSystem"
      class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold"
      :class="isUser ? 'bg-blue-500 text-white' : 'bg-emerald-600 text-white'"
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

        <!-- Input Request -->
        <InputRequestBlock
          v-else-if="part.type === 'request-input'"
          :card="part.inputRequest"
          @submit="emit('submit-input', $event)"
        />

        <!-- System Event -->
        <div
          v-else-if="part.type === 'system-event'"
          class="rounded-md bg-amber-100/70 px-3 py-2 text-xs text-amber-900"
        >
          <div class="font-semibold">{{ part.subtype }}</div>
          <pre class="mt-1 whitespace-pre-wrap">{{ JSON.stringify(part.data, null, 2) }}</pre>
        </div>

      </div>
    </div>
  </div>
</template>
