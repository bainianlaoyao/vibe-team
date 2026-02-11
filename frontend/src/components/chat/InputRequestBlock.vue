<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { InputRequestCard } from '@/types/chat';

const props = defineProps<{
  card: InputRequestCard;
}>();

const emit = defineEmits<{
  (e: 'submit', payload: { questionId: string; answer: string }): void;
}>();

const localAnswer = ref(props.card.answer);

watch(
  () => props.card.answer,
  next => {
    localAnswer.value = next;
  },
);

const isLocked = computed(
  () => props.card.status === 'pending' || props.card.status === 'acknowledged',
);

const statusLabel = computed(() => {
  if (props.card.status === 'pending') return 'Submitting...';
  if (props.card.status === 'acknowledged') return 'Submitted';
  if (props.card.status === 'error') return props.card.errorMessage || 'Submit failed';
  return 'Awaiting input';
});

function submit(answer: string): void {
  if (isLocked.value) return;
  emit('submit', { questionId: props.card.questionId, answer });
}
</script>

<template>
  <section class="mt-3 rounded-lg border border-sky-400/35 bg-sky-500/10 p-3">
    <header class="flex items-center justify-between gap-2">
      <div class="text-[11px] font-semibold uppercase tracking-wide text-sky-700">
        Input Required
      </div>
      <div
        class="text-[11px]"
        :class="
          card.status === 'error'
            ? 'text-red-600'
            : card.status === 'acknowledged'
              ? 'text-green-600'
              : 'text-sky-700'
        "
      >
        {{ statusLabel }}
      </div>
    </header>

    <p class="mt-2 text-sm font-medium text-text-primary whitespace-pre-wrap">
      {{ card.question }}
    </p>

    <div v-if="card.options.length > 0" class="mt-3 flex flex-wrap gap-2">
      <button
        v-for="option in card.options"
        :key="option"
        type="button"
        class="rounded-md border border-border bg-bg-primary px-3 py-1.5 text-xs text-text-primary hover:border-sky-500/60 disabled:cursor-not-allowed disabled:opacity-55"
        :disabled="isLocked"
        @click="submit(option)"
      >
        {{ option }}
      </button>
    </div>

    <form v-else class="mt-3 flex items-center gap-2" @submit.prevent="submit(localAnswer)">
      <input
        v-model="localAnswer"
        type="text"
        class="h-9 flex-1 rounded-md border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none focus:border-sky-500/60"
        :required="card.required"
        :disabled="isLocked"
        placeholder="Type your answer"
      />
      <button
        type="submit"
        class="h-9 rounded-md bg-sky-600 px-3 text-xs font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-55"
        :disabled="isLocked || (card.required && !localAnswer.trim())"
      >
        Submit
      </button>
    </form>

    <div v-if="card.deadlineAt" class="mt-2 text-[11px] text-text-tertiary">
      Deadline: {{ new Date(card.deadlineAt).toLocaleString() }}
    </div>
  </section>
</template>
