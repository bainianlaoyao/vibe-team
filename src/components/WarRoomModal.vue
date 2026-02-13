<script setup lang="ts">
import type { Conflict } from '../types/demo'

defineProps<{
  show: boolean
  conflict: Conflict | null
}>()

const emit = defineEmits<{
  resolve: []
  dismiss: []
}>()

const handleResolve = () => {
  emit('resolve')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="show && conflict"
        class="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-8"
      >
        <div class="w-full max-w-5xl glass-strong rounded-2xl border-2 border-signal-red/30 shadow-2xl animate-pop-in">
          <!-- Header -->
          <div class="px-8 py-6 border-b border-white/10">
            <div class="flex items-center gap-4">
              <div class="w-12 h-12 bg-signal-red/20 rounded-xl flex items-center justify-center animate-pulse">
                <svg class="w-6 h-6 text-signal-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h2 class="text-2xl font-bold text-signal-red">War Room: Conflict Detected</h2>
                <p class="text-white/60 mt-1">{{ conflict.description }}</p>
              </div>
            </div>
          </div>

          <!-- Conflict Content -->
          <div class="p-8">
            <div class="grid grid-cols-3 gap-6">
              <!-- Agent A Position -->
              <div class="glass rounded-xl p-6 border border-white/10">
                <div class="flex items-center gap-3 mb-4">
                  <div class="w-10 h-10 bg-holographic-blue/20 rounded-lg flex items-center justify-center text-xl">
                    🏗️
                  </div>
                  <div>
                    <h3 class="font-semibold">Agent A</h3>
                    <p class="text-xs text-white/40">{{ conflict.agents[0] }}</p>
                  </div>
                </div>
                <div class="space-y-3">
                  <div class="text-sm text-white/60">Believes:</div>
                  <div class="px-4 py-3 bg-holographic-blue/10 border border-holographic-blue/30 rounded-lg font-mono text-sm">
                    user_id: String (UUID)
                  </div>
                </div>
              </div>

              <!-- AI Suggestion (Middle) -->
              <div class="glass-strong rounded-xl p-6 border-2 border-electric-indigo/30">
                <div class="flex items-center gap-3 mb-4">
                  <div class="w-10 h-10 bg-electric-indigo/20 rounded-lg flex items-center justify-center">
                    <svg class="w-5 h-5 text-electric-indigo" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div>
                    <h3 class="font-semibold text-electric-indigo">AI Suggestion</h3>
                    <p class="text-xs text-white/40">Recommended Solution</p>
                  </div>
                </div>
                <div class="space-y-3">
                  <div class="text-sm text-white/60">Analysis:</div>
                  <div class="px-4 py-3 bg-electric-indigo/10 border border-electric-indigo/30 rounded-lg text-sm leading-relaxed">
                    {{ conflict.suggestion }}
                  </div>
                  <div class="mt-4 px-4 py-3 bg-neon-green/10 border border-neon-green/30 rounded-lg">
                    <div class="text-xs text-neon-green font-medium mb-1">✓ Impact:</div>
                    <div class="text-sm text-white/80">Both agents can proceed. Zero breaking changes.</div>
                  </div>
                </div>
              </div>

              <!-- Agent B Position -->
              <div class="glass rounded-xl p-6 border border-white/10">
                <div class="flex items-center gap-3 mb-4">
                  <div class="w-10 h-10 bg-cyber-yellow/20 rounded-lg flex items-center justify-center text-xl">
                    🎨
                  </div>
                  <div>
                    <h3 class="font-semibold">Agent B</h3>
                    <p class="text-xs text-white/40">{{ conflict.agents[1] }}</p>
                  </div>
                </div>
                <div class="space-y-3">
                  <div class="text-sm text-white/60">Believes:</div>
                  <div class="px-4 py-3 bg-cyber-yellow/10 border border-cyber-yellow/30 rounded-lg font-mono text-sm">
                    user_id: Int
                  </div>
                </div>
              </div>
            </div>

            <!-- Resolution Preview -->
            <div class="mt-6 glass rounded-xl p-6">
              <div class="flex items-center justify-between mb-4">
                <h4 class="font-semibold">Resolution Preview</h4>
                <span class="text-xs text-white/40">Code Diff</span>
              </div>
              <div class="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <div class="flex">
                  <div class="w-8 text-red-400 select-none">-</div>
                  <div class="text-red-400 line-through opacity-50">user_id: Int</div>
                </div>
                <div class="flex">
                  <div class="w-8 text-neon-green select-none">+</div>
                  <div class="text-neon-green">user_id: String // @db.UUID</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="px-8 py-6 border-t border-white/10 flex items-center justify-between">
            <button
              @click="emit('dismiss')"
              class="px-6 py-3 text-white/60 hover:text-white transition-colors"
            >
              Dismiss
            </button>
            <div class="flex gap-3">
              <button
                class="px-6 py-3 glass hover:bg-white/10 rounded-xl font-medium transition-colors"
              >
                Manual Resolve
              </button>
              <button
                @click="handleResolve"
                class="px-6 py-3 bg-gradient-to-r from-electric-indigo to-neon-green
                       rounded-xl font-medium text-white shadow-lg shadow-electric-indigo/30
                       hover:shadow-neon-green/30 transition-all hover:scale-[1.02]"
              >
                ✓ Approve AI Fix
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
