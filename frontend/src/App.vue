<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import dagre from 'dagre'

// Styles
import '@vue-flow/core/dist/style.css'

const { fitView } = useVueFlow()

const nodes = ref<any[]>([])
const edges = ref<any[]>([])

// Dagre layout function to automatically position nodes
const getLayoutedElements = (nodes: any[], edges: any[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))

  // Set direction (TB = Top to Bottom)
  dagreGraph.setGraph({ rankdir: direction })

  nodes.forEach((node) => {
    // We assume a standard node size for layout purposes
    dagreGraph.setNode(node.id, { width: 200, height: 60 })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)

    // Calculate layout offset for "Swimlane" effect
    // PM/Dev on Left, Arch/QA on Right
    let xOffset = 0
    const name = node.data?.agent_name || ""

    if (name.includes("PM") || name.includes("Dev")) {
        xOffset = -150
    } else if (name.includes("Arch") || name.includes("QA")) {
        xOffset = 150
    }

    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 100 + xOffset, // Center anchor adjustment + Swimlane
        y: nodeWithPosition.y - 30
      },
    }
  })
}

// Recursive function to flatten the graph
const processGraph = (node: any): { nodes: any[], edges: any[], entries: string[], exits: string[] } => {
  const nodes: any[] = []
  const edges: any[] = []
  let entries: string[] = []
  let exits: string[] = []

  if (!node) return { nodes, edges, entries, exits }

  if (node.type === 'chain') {
    const steps = node.steps || []
    let previousExits: string[] = []

    steps.forEach((step: any, index: number) => {
      const result = processGraph(step)
      nodes.push(...result.nodes)
      edges.push(...result.edges)

      if (index === 0) {
        entries = result.entries
      } else {
        // Connect previous exits to current entries
        previousExits.forEach((source) => {
          result.entries.forEach((target) => {
            edges.push({
              id: `e-${source}-${target}`,
              source,
              target,
              type: 'smoothstep',
              animated: true,
            })
          })
        })
      }
      previousExits = result.exits
    })
    exits = previousExits

  } else if (node.type === 'parallel') {
    const branches = node.branches || []
    branches.forEach((branch: any) => {
      const result = processGraph(branch)
      nodes.push(...result.nodes)
      edges.push(...result.edges)
      // Parallel node starts at all branches
      entries.push(...result.entries)
      // Parallel node ends at all branches
      exits.push(...result.exits)
    })

  } else if (node.type === 'branch') {
    // 1. Process the decision node first
    const decisionResult = processGraph(node.decision_node)
    nodes.push(...decisionResult.nodes)
    edges.push(...decisionResult.edges)

    // The branch starts at the decision node
    entries = decisionResult.entries

    const decisionExits = decisionResult.exits
    const paths = node.paths || {}
    const collectedExits: string[] = []

    // 2. Process each path
    Object.entries(paths).forEach(([choice, pathNode]: [string, any]) => {
      const result = processGraph(pathNode)
      nodes.push(...result.nodes)
      edges.push(...result.edges)

      // Connect decision exits to path entries with label
      decisionExits.forEach((source) => {
        result.entries.forEach((target) => {
          edges.push({
            id: `e-${source}-${target}`,
            source,
            target,
            type: 'smoothstep',
            label: choice, // Label the edge (e.g., "Yes", "No")
            animated: true,
            style: { stroke: choice === 'No' ? '#ef4444' : '#10b981' }, // Red for No, Green for others
            labelStyle: { fill: 'white', fontWeight: 700, fontSize: 12 },
            labelBgStyle: { fill: '#1f2937' },
          })
        })
      })

      collectedExits.push(...result.exits)
    })

    exits = collectedExits

  } else {
    // Leaf Nodes (Task, Human, etc.)
    // Map types to CSS classes
    const cssClass = node.type === 'human' ? 'human-node' : 'agent-node'

    nodes.push({
      id: node.id,
      label: node.name || node.id,
      type: 'default',
      class: cssClass,
      data: { ...node }
    })

    entries = [node.id]
    exits = [node.id]
  }

  return { nodes, edges, entries, exits }
}

onMounted(async () => {
  try {
    // Fetch the recursive flow data
    const response = await fetch('/complex_flow.json')
    const rootNode = await response.json()

    // Flatten the recursive structure
    const { nodes: flatNodes, edges: flatEdges } = processGraph(rootNode)

    // Calculate layout
    const layoutedNodes = getLayoutedElements(flatNodes, flatEdges)

    nodes.value = layoutedNodes
    edges.value = flatEdges

    // Fit view after rendering
    setTimeout(() => {
      fitView()
    }, 50)
  } catch (e) {
    console.error("Failed to load flow data", e)
  }
})
</script>

<template>
  <div class="h-screen w-screen bg-gray-900 text-white overflow-hidden">
    <!-- Overlay UI -->
    <div class="absolute top-6 left-6 z-10 p-5 bg-gray-800/90 backdrop-blur-sm rounded-xl shadow-2xl border border-gray-700 w-80">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-3 h-3 rounded-full bg-purple-500 animate-pulse"></div>
        <h1 class="text-xl font-bold text-white tracking-wide">EXECUTION PLAN</h1>
      </div>
      <p class="text-xs text-gray-400 uppercase tracking-widest mb-4">Live Agent Orchestration</p>

      <div class="space-y-2">
        <div class="flex justify-between text-xs">
          <span class="text-gray-500">Status</span>
          <span class="text-green-400 font-mono">ACTIVE</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-gray-500">Active Agents</span>
          <span class="text-purple-400 font-mono">4</span>
        </div>
        <div class="w-full bg-gray-700 h-1 mt-2 rounded-full overflow-hidden">
          <div class="bg-purple-600 h-full w-2/3"></div>
        </div>
      </div>
    </div>

    <!-- The Graph -->
    <VueFlow
      v-model:nodes="nodes"
      v-model:edges="edges"
      class="basic-flow"
      :default-viewport="{ zoom: 1.2 }"
      :min-zoom="0.2"
      :max-zoom="4"
    >
      <Background pattern-color="#374151" :gap="20" />
      <Controls class="!bg-gray-800 !border-gray-700 !text-white" />
    </VueFlow>
  </div>
</template>

<style>
@import "tailwindcss";

/* --- Global Graph Styles --- */

/* Node Base Style */
.vue-flow__node {
    @apply rounded-lg border border-gray-600 bg-gray-800 text-gray-100 p-4 shadow-xl w-[200px] text-center font-mono text-xs transition-all duration-300;
}

.vue-flow__node:hover {
    @apply scale-105 border-gray-400 z-10;
}

/* Agent Node (Task) - Sci-Fi Purple */
.vue-flow__node-agent-node {
    @apply border-purple-500/50 bg-gray-900/80 shadow-[0_0_20px_rgba(139,92,246,0.2)];
}
.vue-flow__node-agent-node .vue-flow__handle {
    @apply bg-purple-500;
}

/* Human Node (Interaction) - Warning Yellow */
.vue-flow__node-human-node {
    @apply border-yellow-500 bg-yellow-900/20 text-yellow-200 border-2 border-dashed;
}

/* Group Node (Parallel) - Blue Info */
.vue-flow__node-group-node {
    @apply border-blue-500/30 bg-blue-900/10 text-blue-300;
}

/* Edge Styles */
.vue-flow__edge-path {
    stroke: #4b5563;
    stroke-width: 2;
}

.vue-flow__edge.animated .vue-flow__edge-path {
    stroke: #8b5cf6; /* Purple flow */
    stroke-width: 3;
    stroke-dasharray: 10;
    animation: flowAnimation 1s linear infinite;
}

@keyframes flowAnimation {
    from { stroke-dashoffset: 20; }
    to { stroke-dashoffset: 0; }
}
</style>
