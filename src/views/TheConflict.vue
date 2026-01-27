<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import AgentCard from '../components/AgentCard.vue'
import LivePreview from '../components/LivePreview.vue'
import WarRoomModal from '../components/WarRoomModal.vue'
import { useDemoEngine } from '../composables/useDemoEngine'
import { demoScript } from '../data/demo-script'
import type { Agent, PreviewState, Tab, Conflict } from '../types/demo'

const props = defineProps<{
  projectName: string
}>()

// Demo Engine
const { isPlaying, currentTime, play, pause, reset, getCompletedEvents, getProgress } = useDemoEngine(demoScript)

// State
const agents = ref<Agent[]>([
  {
    id: 'backend_01',
    name: 'Schema Architect',
    role: 'architect',
    status: 'idle',
    currentAction: 'Waiting for mission...',
    artifacts: [],
    avatar: '🏗️'
  },
  {
    id: 'frontend_01',
    name: 'UI Builder',
    role: 'frontend',
    status: 'idle',
    currentAction: 'Waiting for mission...',
    artifacts: [],
    avatar: '🎨'
  },
  {
    id: 'design_01',
    name: 'Design System',
    role: 'design',
    status: 'idle',
    currentAction: 'Waiting for mission...',
    artifacts: [],
    avatar: '✨'
  }
])

const previewState = ref<PreviewState>({ type: 'loading', elements: [] })
const activeTab = ref<Tab>('preview')
const terminalOutput = ref<string[]>([])
const commandInput = ref('')
const showWarRoom = ref(false)
const activeConflict = ref<Conflict | null>(null)
const conflictBanner = ref<string | null>(null)

// Simulate conflict scenario
const triggerConflict = () => {
  // Set both agents to error state
  agents.value[0].status = 'error'
  agents.value[0].currentAction = '❌ Schema conflict detected'
  agents.value[1].status = 'error'
  agents.value[1].currentAction = '❌ Type mismatch: user_id'

  // Create conflict
  activeConflict.value = {
    id: 'conflict_001',
    type: 'schema',
    agents: ['backend_01', 'frontend_01'],
    description: 'Schema Mismatch: User ID Type Conflict',
    suggestion: '建议统一使用 String (UUID)，因为我们使用的是 Supabase，它原生支持 UUID 且能避免分布式系统中的 ID 冲突问题。',
    resolved: false
  }

  // Show banner
  conflictBanner.value = '🔴 Dependency Conflict: User Schema mismatch'

  // Show War Room after 2 seconds
  setTimeout(() => {
    showWarRoom.value = true
  }, 2000)

  addTerminalLog('[ERROR] Schema conflict detected between backend_01 and frontend_01')
}

const resolveConflict = () => {
  if (activeConflict.value) {
    activeConflict.value.resolved = true

    // Update agents back to working
    agents.value[0].status = 'coding'
    agents.value[0].currentAction = 'Applying resolution...'
    agents.value[1].status = 'blocked'
    agents.value[1].currentAction = 'Waiting for schema update...'

    addTerminalLog('[INFO] Applying AI-suggested resolution...')

    // Simulate resolution process
    setTimeout(() => {
      agents.value[0].status = 'done'
      agents.value[0].currentAction = '✓ Schema updated'

      agents.value[1].status = 'coding'
      agents.value[1].currentAction = 'Resuming with new schema...'

      conflictBanner.value = null
      showWarRoom.value = false

      addTerminalLog('[SUCCESS] Conflict resolved. All agents operational.')

      // Resume demo
      setTimeout(() => {
        agents.value[1].status = 'done'
        agents.value[1].currentAction = '✓ Sync complete'
      }, 2000)
    }, 1500)
  }
}

const dismissConflict = () => {
  showWarRoom.value = false
}

// Process events
const processEvents = () => {
  const events = getCompletedEvents()

  events.forEach(event => {
    switch (event.event) {
      case 'agent_start':
        updateAgentStatus(event.agent_id, event.status, event.log)
        break
      case 'agent_status_change':
        updateAgentStatus(event.agent_id, event.status, event.log)
        break
      case 'file_created':
        addArtifact(event.agent_id, event.path, event.content_preview)
        addTerminalLog(`[CREATE] ${event.path}`)
        break
      case 'preview_update':
        updatePreview(event.view_state, event.description)
        addTerminalLog(`[PREVIEW] ${event.description}`)
        break
    }
  })
}

const updateAgentStatus = (agentId: string, status: any, log: string) => {
  const agent = agents.value.find(a => a.id === agentId)
  if (agent) {
    agent.status = status
    agent.currentAction = log
  }
}

const addArtifact = (agentId: string, path: string, preview: string) => {
  const agent = agents.value.find(a => a.id === agentId)
  if (agent) {
    const name = path.split('/').pop() || path
    const type = path.includes('component') ? 'component' :
                 path.includes('page') ? 'page' :
                 path.includes('schema') ? 'schema' : 'config'
    agent.artifacts.push({
      name,
      path,
      type,
      timestamp: Date.now()
    })
  }
}

const updatePreview = (state: string, description: string) => {
  const stateMap: Record<string, PreviewState['type']> = {
    'skeleton_screen': 'skeleton',
    'partial': 'partial',
    'full_ui_v1': 'full'
  }

  previewState.value = {
    type: stateMap[state] || 'loading',
    elements: [],
    currentView: description
  }
}

const addTerminalLog = (log: string) => {
  const timestamp = new Date().toLocaleTimeString()
  terminalOutput.value.push(`[${timestamp}] ${log}`)
  if (terminalOutput.value.length > 50) {
    terminalOutput.value.shift()
  }
}

// Watch for event changes
watch(currentTime, () => {
  processEvents()

  // Trigger conflict at specific time (e.g., 8000ms)
  if (currentTime.value >= 8000 && currentTime.value < 8500 && !activeConflict.value) {
    triggerConflict()
  }
})

// Auto-start demo on mount
onMounted(() => {
  setTimeout(() => {
    play()
  }, 500)
})

// Computed
const overallProgress = computed(() => getProgress())
</script>

<template>
  <div class="h-screen flex flex-col">
    <!-- Conflict Banner -->
    <Transition name="banner">
      <div
        v-if="conflictBanner"
        class="bg-signal-red/20 border-b-2 border-signal-red px-6 py-3"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 bg-signal-red/20 rounded-lg flex items-center justify-center animate-pulse">
              <svg class="w-4 h-4 text-signal-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <span class="font-medium text-signal-red">{{ conflictBanner }}</span>
          </div>
          <button
            @click="showWarRoom = true"
            class="px-4 py-2 bg-signal-red hover:bg-signal-red/80 text-white rounded-lg
                   text-sm font-medium transition-colors"
          >
            Open War Room →
          </button>
        </div>
      </div>
    </Transition>

    <!-- Header -->
    <header class="glass border-b border-white/10 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold">{{ projectName }}</h1>
          <div class="h-6 w-px bg-white/10"></div>
          <div class="flex items-center gap-2 text-sm text-white/60">
            <div class="w-2 h-2 rounded-full" :class="isPlaying ? 'bg-neon-green animate-pulse' : 'bg-white/30'"></div>
            {{ isPlaying ? 'Live' : 'Paused' }}
          </div>
          <div class="ml-4 px-3 py-1 bg-signal-red/20 text-signal-red rounded-lg text-xs font-medium">
            Conflict Demo Mode
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="flex-1 mx-12">
          <div class="flex items-center gap-3">
            <span class="text-sm text-white/60 font-mono">{{ overallProgress.toFixed(0) }}%</span>
            <div class="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
              <div
                class="h-full transition-all duration-300"
                :class="activeConflict ? 'bg-signal-red' : 'bg-gradient-to-r from-electric-indigo to-holographic-blue'"
                :style="{ width: `${overallProgress}%` }"
              ></div>
            </div>
          </div>
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-2">
          <button
            @click="isPlaying ? pause() : play()"
            class="px-4 py-2 glass rounded-lg hover:bg-white/10 transition-colors"
          >
            {{ isPlaying ? '⏸ Pause' : '▶ Play' }}
          </button>
          <button
            @click="reset"
            class="px-4 py-2 glass rounded-lg hover:bg-white/10 transition-colors"
          >
            ↺ Reset
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left Panel: Tactical Radar (40%) -->
      <aside class="w-2/5 border-r border-white/10 flex flex-col">
        <!-- Agent Squad -->
        <div class="flex-1 overflow-y-auto p-6">
          <h2 class="text-sm uppercase tracking-wider text-white/40 mb-4">Agent Squad</h2>
          <div class="space-y-3">
            <AgentCard
              v-for="agent in agents"
              :key="agent.id"
              :agent="agent"
            />
          </div>

          <!-- Conflict Indicator -->
          <div v-if="activeConflict" class="mt-6 glass rounded-xl p-4 border border-signal-red/30 animate-pulse">
            <div class="flex items-center gap-3 mb-3">
              <div class="w-8 h-8 bg-signal-red/20 rounded-lg flex items-center justify-center">
                ⚠️
              </div>
              <div>
                <h4 class="font-semibold text-signal-red">Active Conflict</h4>
                <p class="text-xs text-white/60">{{ activeConflict.description }}</p>
              </div>
            </div>
            <button
              @click="showWarRoom = true"
              class="w-full py-2 bg-signal-red hover:bg-signal-red/80 rounded-lg text-sm font-medium transition-colors"
            >
              Resolve Now
            </button>
          </div>
        </div>

        <!-- Dependency Graph Mini -->
        <div class="h-48 border-t border-white/10 p-6">
          <h2 class="text-sm uppercase tracking-wider text-white/40 mb-4">Dependency Graph</h2>
          <div class="h-full bg-white/5 rounded-lg flex items-center justify-center">
            <div class="grid grid-cols-3 gap-4">
              <div
                v-for="agent in agents"
                :key="agent.id"
                class="text-center"
              >
                <div
                  class="w-10 h-10 mx-auto rounded-lg flex items-center justify-center text-lg mb-2"
                  :class="{
                    'bg-neon-green/20': agent.status === 'done',
                    'bg-holographic-blue/20': agent.status === 'coding',
                    'bg-cyber-yellow/20': agent.status === 'blocked',
                    'bg-signal-red/20 animate-pulse': agent.status === 'error',
                    'bg-white/10': agent.status === 'idle'
                  }"
                >
                  {{ agent.avatar }}
                </div>
                <div class="w-px h-8 bg-white/20 mx-auto"></div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right Panel: Context Stage (60%) -->
      <main class="flex-1 flex flex-col">
        <!-- Tabs -->
        <div class="flex border-b border-white/10">
          <button
            v-for="tab in ['preview', 'terminal', 'diff']"
            :key="tab"
            @click="activeTab = tab"
            class="px-6 py-3 text-sm font-medium capitalize transition-colors"
            :class="activeTab === tab ? 'text-electric-indigo border-b-2 border-electric-indigo' : 'text-white/60 hover:text-white/80'"
          >
            {{ tab === 'diff' ? 'Code Diff' : tab }}
          </button>
        </div>

        <!-- Tab Content -->
        <div class="flex-1 overflow-hidden">
          <!-- Live Preview -->
          <div v-if="activeTab === 'preview'" class="h-full p-6">
            <LivePreview :preview-state="previewState" />
          </div>

          <!-- Terminal -->
          <div v-else-if="activeTab === 'terminal'" class="h-full p-6">
            <div class="h-full bg-black/50 rounded-xl font-mono text-sm overflow-auto p-4">
              <div v-for="(log, i) in terminalOutput" :key="i" class="text-white/70 mb-1">
                {{ log }}
              </div>
              <div v-if="terminalOutput.length === 0" class="text-white/30">
                Waiting for activity...
              </div>
            </div>
          </div>

          <!-- Code Diff -->
          <div v-else class="h-full p-6">
            <div class="h-full bg-white/5 rounded-xl flex items-center justify-center">
              <p class="text-white/40">Code changes will appear here</p>
            </div>
          </div>
        </div>

        <!-- Broadcast Bar -->
        <div class="border-t border-white/10 p-4">
          <div class="flex items-center gap-3">
            <div class="flex-1 relative">
              <input
                v-model="commandInput"
                type="text"
                placeholder="给所有 Agent 下达指令..."
                class="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl
                       focus:outline-none focus:border-electric-indigo/50 focus:bg-white/10
                       transition-all placeholder:text-white/30"
              >
              <div class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-white/30">
                ⌘K
              </div>
            </div>
            <button class="px-6 py-3 bg-electric-indigo hover:bg-electric-indigo/80 rounded-xl font-medium transition-colors">
              Send
            </button>
          </div>
        </div>
      </main>
    </div>

    <!-- War Room Modal -->
    <WarRoomModal
      :show="showWarRoom"
      :conflict="activeConflict"
      @resolve="resolveConflict"
      @dismiss="dismissConflict"
    />
  </div>
</template>

<style scoped>
.banner-enter-active,
.banner-leave-active {
  transition: all 0.3s ease;
}

.banner-enter-from,
.banner-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}
</style>
