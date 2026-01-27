<script setup lang="ts">
import { ref } from 'vue'
import type { ProjectManifesto } from '../types/demo'

const emit = defineEmits<{
  complete: [manifesto: ProjectManifesto]
}>()

const input = ref('')
const isAnimating = ref(false)
const showManifesto = ref(false)
const manifesto = ref<ProjectManifesto | null>(null)

const handleInput = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && input.value.trim()) {
    startAnimation()
  }
}

const startAnimation = () => {
  isAnimating.value = true

  // Simulate AI processing
  setTimeout(() => {
    manifesto.value = {
      name: input.value,
      stack: ['Next.js 14', 'TypeScript', 'Tailwind CSS', 'Supabase'],
      entities: ['User', 'Subscription', 'PaymentEvent', 'Invoice'],
      pages: ['/dashboard', '/settings', '/api/webhooks/stripe'],
      description: 'SaaS Revenue Analytics Dashboard'
    }
    showManifesto.value = true
  }, 2000)
}

const authorizeAndStart = () => {
  if (manifesto.value) {
    emit('complete', manifesto.value)
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-8">
    <!-- Input Phase -->
    <div
      v-if="!isAnimating"
      class="w-full max-w-3xl transition-all duration-700"
    >
      <div class="text-center mb-12">
        <h1 class="text-5xl font-bold mb-4 bg-gradient-to-r from-electric-indigo to-holographic-blue bg-clip-text text-transparent">
          What will you build today?
        </h1>
        <p class="text-white/60 text-lg">
          Describe your idea, and watch the AI team bring it to life
        </p>
      </div>

      <div class="relative">
        <input
          v-model="input"
          type="text"
          placeholder="e.g., 做一个面向独立开发者的 SaaS 收入看板，要有 Stripe 集成..."
          class="w-full px-8 py-6 text-xl glass rounded-2xl border-2 border-transparent
                 focus:border-electric-indigo focus:outline-none focus:shadow-lg
                 focus:shadow-electric-indigo/20 transition-all duration-300
                 placeholder:text-white/30"
          @keyup="handleInput"
        />
        <div class="absolute right-6 top-1/2 -translate-y-1/2 text-white/30">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
      </div>

      <div class="mt-8 text-center">
        <p class="text-white/40 text-sm">Press Enter to unleash your AI team</p>
      </div>
    </div>

    <!-- Architect Core Animation -->
    <div
      v-else-if="isAnimating && !showManifesto"
      class="text-center"
    >
      <div class="relative w-64 h-64 mx-auto mb-8">
        <!-- Rotating rings -->
        <div class="absolute inset-0 border-4 border-electric-indigo/30 rounded-full animate-spin-slow"></div>
        <div class="absolute inset-4 border-4 border-holographic-blue/30 rounded-full animate-spin" style="animation-direction: reverse;"></div>
        <div class="absolute inset-8 border-4 border-electric-indigo/20 rounded-full animate-spin-slow"></div>

        <!-- Core -->
        <div class="absolute inset-0 flex items-center justify-center">
          <div class="w-24 h-24 bg-gradient-to-br from-electric-indigo to-holographic-blue rounded-full animate-pulse-glow"></div>
        </div>
      </div>
      <p class="text-xl text-white/60 animate-pulse">Architect Core is thinking...</p>
    </div>

    <!-- Manifesto Card -->
    <div
      v-else-if="showManifesto && manifesto"
      class="w-full max-w-2xl animate-pop-in"
    >
      <div class="glass-strong rounded-3xl p-8 border border-electric-indigo/30">
        <div class="flex items-center gap-4 mb-6">
          <div class="w-12 h-12 bg-gradient-to-br from-electric-indigo to-holographic-blue rounded-xl flex items-center justify-center">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h2 class="text-2xl font-bold">{{ manifesto.name }}</h2>
            <p class="text-white/60">{{ manifesto.description }}</p>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-6">
          <!-- Stack -->
          <div>
            <h3 class="text-sm uppercase tracking-wider text-white/40 mb-3">Golden Stack</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="tech in manifesto.stack"
                :key="tech"
                class="px-3 py-1 bg-electric-indigo/20 text-electric-indigo rounded-lg text-sm font-mono"
              >
                {{ tech }}
              </span>
            </div>
          </div>

          <!-- Entities -->
          <div>
            <h3 class="text-sm uppercase tracking-wider text-white/40 mb-3">Data Entities</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="entity in manifesto.entities"
                :key="entity"
                class="px-3 py-1 bg-holographic-blue/20 text-holographic-blue rounded-lg text-sm font-mono"
              >
                {{ entity }}
              </span>
            </div>
          </div>

          <!-- Pages -->
          <div class="col-span-2">
            <h3 class="text-sm uppercase tracking-wider text-white/40 mb-3">Pages & Routes</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="page in manifesto.pages"
                :key="page"
                class="px-3 py-1 bg-white/10 text-white/80 rounded-lg text-sm font-mono"
              >
                {{ page }}
              </span>
            </div>
          </div>
        </div>

        <button
          @click="authorizeAndStart"
          class="w-full mt-8 py-4 bg-gradient-to-r from-electric-indigo to-holographic-blue
                 rounded-xl font-semibold text-lg shadow-lg shadow-electric-indigo/30
                 hover:shadow-electric-indigo/50 hover:scale-[1.02]
                 active:scale-[0.98] transition-all duration-200"
        >
          AUTHORIZE TEAM & START
        </button>
      </div>
    </div>
  </div>
</template>
