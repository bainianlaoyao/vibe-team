<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import AgentCard from '../components/AgentCard.vue'
import LivePreview from '../components/LivePreview.vue'
import { useDemoEngine } from '../composables/useDemoEngine'
import { demoScript } from '../data/demo-script'
import type { Agent, PreviewState, Tab } from '../types/demo'

defineProps<{
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

const addArtifact = (agentId: string, path: string, _preview: string) => {
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
  // Keep only last 50 lines
  if (terminalOutput.value.length > 50) {
    terminalOutput.value.shift()
  }
}

// Watch for event changes
watch(currentTime, () => {
  processEvents()
})

// Auto-start demo on mount
onMounted(() => {
  setTimeout(() => {
    play()
  }, 500)
})

// Computed
const overallProgress = computed(() => getProgress())
const tabs: Tab[] = ['preview', 'terminal', 'diff']
</script>

<template>
  <div class="h-screen flex flex-col">
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
        </div>

        <!-- Progress Bar -->
        <div class="flex-1 mx-12">
          <div class="flex items-center gap-3">
            <span class="text-sm text-white/60 font-mono">{{ overallProgress.toFixed(0) }}%</span>
            <div class="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
              <div
                class="h-full bg-gradient-to-r from-electric-indigo to-holographic-blue transition-all duration-300"
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
            v-for="tab in tabs"
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
  </div>
</template>
