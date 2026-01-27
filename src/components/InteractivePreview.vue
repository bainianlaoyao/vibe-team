<script setup lang="ts">
import { ref, computed } from 'vue'
import DirectiveModal from './DirectiveModal.vue'
import type { PreviewState } from '../types/demo'

const props = defineProps<{
  previewState: PreviewState
}>()

const emit = defineEmits<{
  directive: [element: string, instruction: string]
}>()

const showDirective = ref(false)
const selectedElement = ref('')
const clickPosition = ref({ x: 0, y: 0 })

const handleElementClick = (e: MouseEvent, elementName: string) => {
  e.stopPropagation()
  selectedElement.value = elementName
  clickPosition.value = { x: e.clientX, y: e.clientY }
  showDirective.value = true
}

const handleDirectiveSubmit = (instruction: string) => {
  emit('directive', selectedElement.value, instruction)
  showDirective.value = false
}

const previewContent = computed(() => {
  const state = props.previewState

  if (state.type === 'loading') {
    return {
      title: 'Initializing...',
      elements: []
    }
  }

  if (state.type === 'skeleton') {
    return {
      title: 'Building UI Structure...',
      elements: ['Navbar', 'Sidebar', 'Container']
    }
  }

  if (state.type === 'partial') {
    return {
      title: 'Loading Content...',
      elements: ['Navbar', 'Sidebar', 'Dashboard', 'Stats Cards (empty)']
    }
  }

  return {
    title: 'Dashboard',
    elements: ['Navbar', 'Sidebar', 'Dashboard', 'Stats Cards', 'Chart', 'Revenue Table']
  }
})
</script>

<template>
  <div class="h-full bg-white rounded-xl overflow-hidden shadow-2xl relative">
    <!-- Browser Chrome -->
    <div class="bg-gray-100 px-4 py-2 flex items-center gap-2 border-b border-gray-200">
      <div class="flex gap-1.5">
        <div class="w-3 h-3 rounded-full bg-red-400"></div>
        <div class="w-3 h-3 rounded-full bg-yellow-400"></div>
        <div class="w-3 h-3 rounded-full bg-green-400"></div>
      </div>
      <div class="flex-1 ml-4">
        <div class="bg-white rounded-md px-3 py-1 text-xs text-gray-600 font-mono">
          localhost:3000/dashboard
        </div>
      </div>
    </div>

    <!-- Preview Content -->
    <div class="h-[calc(100%-44px)] bg-gray-50 p-8">
      <!-- Loading State -->
      <div v-if="previewState.type === 'loading'" class="h-full flex items-center justify-center">
        <div class="text-center">
          <div class="w-16 h-16 border-4 border-electric-indigo/20 border-t-electric-indigo rounded-full animate-spin mx-auto mb-4"></div>
          <p class="text-gray-500 font-medium">{{ previewContent.title }}</p>
        </div>
      </div>

      <!-- Interactive App UI -->
      <div v-else class="space-y-4">
        <!-- Simulated App UI -->
        <div class="bg-white rounded-lg shadow-sm p-6">
          <div class="flex items-center justify-between mb-6">
            <div class="h-8 bg-gray-200 rounded w-48 animate-pulse"></div>
            <button
              @click="(e) => handleElementClick(e, 'Settings Button')"
              class="h-8 px-3 bg-gray-100 hover:bg-electric-indigo/20 rounded-lg text-sm text-gray-600
                     transition-colors cursor-pointer border border-transparent hover:border-electric-indigo/30"
              title="Click to modify"
            >
              Settings ⚙️
            </button>
          </div>

          <div class="grid grid-cols-3 gap-4 mb-6">
            <div
              v-for="(stat, i) in ['Revenue', 'Users', 'Conversion']"
              :key="stat"
              class="bg-gray-50 rounded-lg p-4 hover:bg-electric-indigo/5 transition-colors cursor-pointer border border-transparent hover:border-electric-indigo/20"
              @click="(e) => handleElementClick(e, `${stat} Card`)"
            >
              <div class="h-4 bg-gray-200 rounded w-20 mb-2 animate-pulse"></div>
              <div class="h-8 bg-gray-300 rounded w-16 animate-pulse"></div>
            </div>
          </div>

          <div v-if="previewState.type === 'full'" class="space-y-4">
            <div
              class="bg-gray-50 rounded-lg p-4 hover:bg-electric-indigo/5 transition-colors cursor-pointer border border-transparent hover:border-electric-indigo/20"
              @click="(e) => handleElementClick(e, 'Chart Component')"
            >
              <div class="h-4 bg-gray-200 rounded w-32 mb-4 animate-pulse"></div>
              <div class="h-32 bg-gradient-to-r from-electric-indigo/10 to-holographic-blue/10 rounded-lg"></div>
            </div>

            <div
              class="bg-gray-50 rounded-lg p-4 hover:bg-electric-indigo/5 transition-colors cursor-pointer border border-transparent hover:border-electric-indigo/20"
              @click="(e) => handleElementClick(e, 'Revenue Table')"
            >
              <div class="h-4 bg-gray-200 rounded w-32 mb-4 animate-pulse"></div>
              <div class="space-y-2">
                <div v-for="i in 3" :key="i" class="h-3 bg-white/60 rounded w-full"></div>
              </div>
            </div>
          </div>
          <div v-else class="bg-gray-100 rounded-lg p-8 animate-pulse">
            <div class="h-32 flex items-center justify-center text-gray-400">
              {{ previewContent.title }}
            </div>
          </div>
        </div>
      </div>

      <!-- Tooltip hint -->
      <div class="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-black/70 text-white text-sm rounded-full">
        💡 Click any element to send directive
      </div>
    </div>

    <!-- Directive Modal -->
    <DirectiveModal
      :show="showDirective"
      :target-element="selectedElement"
      :position="clickPosition"
      @close="showDirective = false"
      @submit="handleDirectiveSubmit"
    />
  </div>
</template>
