import asyncio
import uuid
import json
from dataclasses import asdict
from typing import List, Dict, Any

# Reuse existing core models, but we will serialize them differently
from agent_flow import AgentArchetype, parallel, ask_human, _ctx, NodeType

def generate_graph_json() -> str:
    """
    Generates a JSON structure compatible with Vue Flow / React Flow.
    """
    nodes = []
    edges = []

    # We need to calculate layout positions ideally, but for now we'll let
    # the frontend (using dagre or elkjs) handle the auto-layout.
    # We just provide structure.

    processed_ids = set()

    for event in _ctx.events:
        if event.id in processed_ids:
            continue

        processed_ids.add(event.id)

        # Map backend types to frontend component types
        # e.g., 'task' -> 'AgentNode', 'human' -> 'InteractionNode'
        frontend_type = "default"
        if event.type == NodeType.TASK:
            frontend_type = "agent-node"
        elif event.type == NodeType.HUMAN:
            frontend_type = "human-node"
        elif event.type == NodeType.PARALLEL:
            frontend_type = "group-node"

        # Construct Node
        node = {
            "id": event.id,
            "type": frontend_type,
            "data": {
                "label": event.name,
                "status": event.status,
                "details": event.details
            },
            "position": {"x": 0, "y": 0} # Placeholder, frontend handles layout
        }
        nodes.append(node)

        # Construct Edge
        if event.parent_id:
            edge = {
                "id": f"e-{event.parent_id}-{event.id}",
                "source": event.parent_id,
                "target": event.id,
                "animated": True if event.status == "running" else False,
                "style": {"stroke": "#8B5CF6"} if event.status == "running" else {}
            }
            edges.append(edge)

    return json.dumps({"nodes": nodes, "edges": edges}, indent=2)

async def main():
    print("--- 🚀 Starting Plan-as-Code Execution (JSON Mode) ---")

    # Clear previous context for clean run
    _ctx.events = []
    _ctx._current_parent = None

    # Setup Agents
    architect = AgentArchetype("Architect", ["System Design"])
    coder = AgentArchetype("Coder", ["Vue", "Python"])

    arch = architect.spawn("Arch-Bot")
    dev = coder.spawn("Dev-Bot")

    # Execution
    root_plan = await arch.do("Design System Architecture")

    await parallel(
        dev.do("Setup Frontend Repo"),
        dev.do("Setup Backend Repo")
    )

    await ask_human("Deploy to production?", ["Yes", "No"])

    print("--- 🏁 Execution Finished ---")

    # Generate JSON
    json_output = generate_graph_json()

    output_file = "poc/plan_as_code/trace_graph.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json_output)

    print(f"\n✅ Graph JSON saved to {output_file}")
    # Print a snippet to show structure
    print("\nSnippet of generated JSON:")
    print(json_output[:500] + "...")

if __name__ == "__main__":
    asyncio.run(main())
