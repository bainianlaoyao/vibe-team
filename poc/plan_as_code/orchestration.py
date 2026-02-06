import asyncio
from agent_flow import AgentArchetype, HumanDecision, Runner

async def main():
    print("--- 🚀 Starting Plan-as-Code Execution (DSL Version) ---")

    # 1. Define Archetypes
    architect = AgentArchetype("Architect", ["System Design", "Tech Stack Selection"])
    frontend_dev = AgentArchetype("FrontendDev", ["Vue", "Tailwind"])
    backend_dev = AgentArchetype("BackendDev", ["Python", "FastAPI"])
    qa_bot = AgentArchetype("QA_Bot", ["Testing", "Security Scan"])

    # 2. Spawn Instances
    arch_lead = architect.spawn("Arch-Lead")
    fe_coder = frontend_dev.spawn("FE-Coder")
    be_coder = backend_dev.spawn("BE-Coder")
    qa_tester = qa_bot.spawn("QA-Tester")

    # 3. Define the Flow using DSL (>> for serial, & for parallel)
    # Flow: Architect -> Human Decision -> (Frontend & Backend) -> QA

    plan = (
        arch_lead.task("Analyze requirements and create technical spec")
        >> HumanDecision("Which database should we use?", ["PostgreSQL", "MongoDB"])
        >> (
            fe_coder.task("Scaffold Vue 3 project structure")
            & be_coder.task("Initialize FastAPI project")
        )
        >> (
            fe_coder.task("Implement Login Component")
            & be_coder.task("Implement Auth API endpoints")
        )
        >> qa_tester.task("Run integration tests")
    )

    # 4. Generate Visualization BEFORE execution
    print("\n--- 📊 Mermaid Graph ---")
    mermaid_code = Runner.visualize(plan)
    print(mermaid_code)

    # Save to file
    output_file = "poc/plan_as_code/plan_graph.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Plan Execution Graph\n\n")
        f.write("```mermaid\n")
        f.write(mermaid_code)
        f.write("\n```\n")
    print(f"\n✅ Graph saved to {output_file}")

    # 5. Execute the Plan
    print("\n--- 🎬 Executing Plan ---")
    await Runner.execute(plan)

if __name__ == "__main__":
    asyncio.run(main())
