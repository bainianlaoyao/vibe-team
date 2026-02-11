<script setup lang="ts">
import { ref, nextTick } from 'vue';

const props = defineProps<{
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'submit', value: string): void;
}>();

const inputValue = ref('');
const textareaRef = ref<HTMLTextAreaElement | null>(null);

function adjustHeight() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
}

function submit() {
  const content = inputValue.value.trim();
  if (!content || props.isLoading) return;

  emit('submit', content);
  inputValue.value = '';
  nextTick(() => adjustHeight());
}
</script>

<template>
  <div class="relative w-full max-w-4xl mx-auto">
    <div class="relative bg-zinc-800 rounded-xl border border-zinc-700 shadow-xl overflow-hidden focus-within:ring-2 focus-within:ring-purple-500/50 focus-within:border-purple-500 transition-all duration-200">
      <textarea
        ref="textareaRef"
        v-model="inputValue"
        @input="adjustHeight"
        @keydown="handleKeydown"
        placeholder="Type a message or /command..."
        rows="1"
        class="w-full bg-transparent text-gray-100 px-4 py-3 pr-12 outline-none resize-none max-h-[200px] min-h-[52px] scrollbar-thin scrollbar-thumb-zinc-600 scrollbar-track-transparent font-sans"
      ></textarea>

      <button
        @click="submit"
        :disabled="isLoading || !inputValue.trim()"
        class="absolute right-2 bottom-2 p-1.5 rounded-lg transition-colors"
        :class="inputValue.trim() && !isLoading ? 'bg-purple-600 text-white hover:bg-purple-500' : 'bg-transparent text-zinc-500 cursor-not-allowed'"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
          <path d="M15.854.146a.5.5 0 0 1 .11.54l-5.819 14.547a.75.75 0 0 1-1.329.124l-3.178-4.995L.643 7.184a.75.75 0 0 1 .124-1.33L15.314.037a.5.5 0 0 1 .54.11ZM6.636 10.07l2.761 4.338L14.13 2.576 6.636 10.07Zm6.787-8.201L1.591 6.602l4.339 2.76 7.494-7.493Z"/>
        </svg>
      </button>
    </div>

    <div class="mt-2 text-center text-xs text-zinc-500">
      <span class="mr-2">↵ Send</span>
      <span class="mr-2">⇧ ↵ New line</span>
    </div>
  </div>
</template>
