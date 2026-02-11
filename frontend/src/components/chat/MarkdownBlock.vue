<script setup lang="ts">
import { computed } from 'vue';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';

const props = defineProps<{
  content: string;
}>();

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
});

const renderedContent = computed(() => {
  const rawHtml = md.render(props.content || '');
  return DOMPurify.sanitize(rawHtml);
});
</script>

<template>
  <div
    class="markdown-body prose prose-invert prose-sm max-w-none break-words"
    v-html="renderedContent"
  ></div>
</template>

<style>
/* Basic styles in case Tailwind Typography isn't fully configured */
.markdown-body pre {
  background-color: #1e1e1e;
  padding: 1rem;
  border-radius: 0.5rem;
  overflow-x: auto;
}
.markdown-body code {
  font-family: monospace;
  background-color: rgba(255,255,255,0.1);
  padding: 0.2em 0.4em;
  border-radius: 3px;
}
</style>
