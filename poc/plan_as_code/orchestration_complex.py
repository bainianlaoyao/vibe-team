import asyncio
import json
from agent_flow import AgentArchetype, HumanDecision, Runner, Branch

async def main():
    print("--- 🚀 Starting Complex Workflow Generation ---")

    # 1. Define Archetypes
    pm_arch = AgentArchetype("ProductManager", ["Requirements", "User Stories"])
    architect_arch = AgentArchetype("Architect", ["System Design", "Feasibility"])
    dev_arch = AgentArchetype("Developer", ["Python", "Logic"])
    fe_arch = AgentArchetype("Frontend_Dev", ["Vue", "TypeScript"]) # Added Frontend
    qa_arch = AgentArchetype("QA_Engineer", ["Testing", "Review"])

    # 2. Spawn Agents
    pm = pm_arch.spawn("PM-Alice")
    arch = architect_arch.spawn("Arch-Bob")
    dev = dev_arch.spawn("Dev-Charlie")
    fe = fe_arch.spawn("FE-Frank") # Added FE Agent
    qa = qa_arch.spawn("QA-Dave")

    # 3. Define the Phases

    # Phase A: Debate & Requirements (Sequential)
    debate_phase = (
        pm.task("Draft initial requirement for Smart Search")
        >> arch.task("Review requirements for performance feasibility")
        >> pm.task("Refine requirements based on technical feedback")
    )

    # Phase B: Planning
    planning_phase = arch.task("Create technical specification and API design")

    # Path 1: Approval -> Execution (Parallel + Sequence)
    # Backend and Frontend work in parallel, then QA tests
    backend_work = dev.task("Implement Smart Search API")
    frontend_work = fe.task("Implement Search UI Components")

    execution_phase = (
        (backend_work & frontend_work) # 🔀 PARALLEL
        >> qa.task("Integration & Acceptance Testing")
    )

    # Path 2: Rejection -> Revision
    revision_phase = (
        pm.task("Analyze rejection reasons")
        >> arch.task("Revise Technical Specification")
    )

    # 4. Define Branching Logic
    decision_node = HumanDecision("Approve Tech Spec?", ["Yes", "No"])

    branching_phase = Branch(decision_node, {
        "Yes": execution_phase,
        "No": revision_phase
    })

    # 5. Combine all phases
    # Debate -> Plan -> Decision -> [Exec | Revise] -> Wrap Up
    complex_plan = (
        debate_phase
        >> planning_phase
        >> branching_phase
        >> pm.task("Project Retrospective & Closure") # Both paths converge here
    )

    # 6. Generate JSON
    print("\n--- 📋 JSON Representation ---")
    json_output = Runner.to_json(complex_plan)
    # print(json_output) # Optional: comment out to reduce noise

    # Save to file
    output_file = "poc/plan_as_code/complex_flow.json"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json_output)
    print(f"\n✅ JSON saved to {output_file}")

    # 7. Generate Mermaid for reference
    print("\n--- 📊 Mermaid Graph ---")
    print(Runner.visualize(complex_plan))

if __name__ == "__main__":
    asyncio.run(main())
