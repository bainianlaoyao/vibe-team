<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TheGenesis from './views/TheGenesis.vue'
import MissionControl from './views/MissionControl.vue'
import TheShoulderTap from './views/TheShoulderTap.vue'
import TheConflict from './views/TheConflict.vue'

type Screen = 'genesis' | 'mission-control' | 'shoulder-tap' | 'conflict'

const currentScreen = ref<Screen>('genesis')
const projectName = ref('')

const handleGenesisComplete = (name: string) => {
  projectName.value = name
  currentScreen.value = 'mission-control'
}

// Screen selector for demo purposes (you can remove this in production)
const screenOptions: { key: Screen; label: string; description: string }[] = [
  { key: 'genesis', label: 'Screen 1', description: 'The Genesis' },
  { key: 'mission-control', label: 'Screen 2', description: 'Mission Control' },
  { key: 'shoulder-tap', label: 'Screen 3', description: 'The Shoulder Tap' },
  { key: 'conflict', label: 'Screen 4', description: 'The Conflict' }
]

onMounted(() => {
  console.log('🚀 Surface Demo initialized')
  console.log('💡 Tip: Open browser console to access screen switcher')
})

// Expose to window for easy screen switching during demo
;(window as any).switchScreen = (screen: Screen) => {
  currentScreen.value = screen
}
</script>

<template>
  <div class="min-h-screen grid-bg">
    <!-- Screen Selector (Demo Only) -->
    <div class="fixed top-4 right-4 z-50">
      <div class="glass rounded-xl p-3 border border-white/10">
        <div class="text-xs text-white/40 mb-2 font-mono">DEMO SCREENS</div>
        <div class="space-y-1">
          <button
            v-for="screen in screenOptions"
            :key="screen.key"
            @click="currentScreen = screen.key"
            class="block w-full px-3 py-2 text-left text-xs rounded-lg transition-all"
            :class="currentScreen === screen.key
              ? 'bg-electric-indigo/30 text-electric-indigo font-medium'
              : 'text-white/60 hover:bg-white/5 hover:text-white/80'"
          >
            <div>{{ screen.label }}</div>
            <div class="opacity-60 scale-90 origin-left">{{ screen.description }}</div>
          </button>
        </div>
      </div>
    </div>

    <TheGenesis
      v-if="currentScreen === 'genesis'"
      @complete="handleGenesisComplete"
    />

    <MissionControl
      v-else-if="currentScreen === 'mission-control'"
      :project-name="projectName || 'Demo Project'"
    />

    <TheShoulderTap
      v-else-if="currentScreen === 'shoulder-tap'"
      :project-name="projectName || 'Demo Project'"
    />

    <TheConflict
      v-else-if="currentScreen === 'conflict'"
      :project-name="projectName || 'Demo Project'"
    />
  </div>
</template>

<style scoped>
</style>
