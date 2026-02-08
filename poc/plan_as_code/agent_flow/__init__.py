import asyncio
import uuid
import json
from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional

# --- Core Node Definitions ---

class Node(ABC):
    def __init__(self, name: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.name = name or self.__class__.__name__

    @abstractmethod
    async def run(self, context: Optional[Dict[str, Any]] = None) -> Any:
        pass

    @abstractmethod
    def to_mermaid(self) -> str:
        """Returns the Mermaid graph definition for this node and its children."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Returns a dictionary representation of the node."""
        pass

    @abstractmethod
    def get_entry_ids(self) -> List[str]:
        """Returns IDs of nodes that accept incoming connections."""
        pass

    @abstractmethod
    def get_exit_ids(self) -> List[str]:
        """Returns IDs of nodes that provide outgoing connections."""
        pass

    def __rshift__(self, other: "Node") -> "Chain":
        """Implements the >> operator for chaining tasks."""
        if isinstance(self, Chain):
            return Chain([*self.steps, other])
        return Chain([self, other])

    def __and__(self, other: "Node") -> "Parallel":
        """Implements the & operator for parallel execution."""
        if isinstance(self, Parallel):
            return Parallel([*self.branches, other])
        return Parallel([self, other])

# --- Concrete Node Implementations ---

class Task(Node):
    def __init__(self, agent: "AgentInstance", instruction: str):
        super().__init__(name=f"{agent.name}: {instruction}")
        self.agent = agent
        self.instruction = instruction

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Any:
        print(f"▶ [{self.agent.name}] Starting task: {self.instruction}")
        result = await self.agent.do(self.instruction)
        return result

    def to_mermaid(self) -> str:
        safe_name = self.name.replace('"', "'").replace(":", "-")
        return f'{self.id}["{safe_name}"]:::task'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "task",
            "name": self.name,
            "agent_name": self.agent.name,
            "instruction": self.instruction
        }

    def get_entry_ids(self) -> List[str]:
        return [self.id]

    def get_exit_ids(self) -> List[str]:
        return [self.id]

class Chain(Node):
    def __init__(self, steps: List[Node]):
        super().__init__(name="Sequence")
        self.steps = steps

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Any:
        result = None
        for step in self.steps:
            result = await step.run(context)
        return result

    def to_mermaid(self) -> str:
        definitions = [step.to_mermaid() for step in self.steps]
        links = []

        for i in range(len(self.steps) - 1):
            current = self.steps[i]
            nxt = self.steps[i+1]

            for exit_id in current.get_exit_ids():
                for entry_id in nxt.get_entry_ids():
                    links.append(f"{exit_id} --> {entry_id}")

        return "\n".join(definitions + links)

    def get_entry_ids(self) -> List[str]:
        return self.steps[0].get_entry_ids() if self.steps else []

    def get_exit_ids(self) -> List[str]:
        return self.steps[-1].get_exit_ids() if self.steps else []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "chain",
            "steps": [step.to_dict() for step in self.steps]
        }

    def __rshift__(self, other: Node) -> "Chain":
        return Chain([*self.steps, other])

class Parallel(Node):
    def __init__(self, branches: List[Node]):
        super().__init__(name="Parallel Group")
        self.branches = branches

    async def run(self, context: Optional[Dict[str, Any]] = None) -> List[Any]:
        print(f"🔀 Executing {len(self.branches)} tasks in parallel...")
        tasks = [branch.run(context) for branch in self.branches]
        return await asyncio.gather(*tasks)

    def to_mermaid(self) -> str:
        return "\n".join([branch.to_mermaid() for branch in self.branches])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "parallel",
            "branches": [branch.to_dict() for branch in self.branches]
        }

    def get_entry_ids(self) -> List[str]:
        ids = []
        for branch in self.branches:
            ids.extend(branch.get_entry_ids())
        return ids

    def get_exit_ids(self) -> List[str]:
        ids = []
        for branch in self.branches:
            ids.extend(branch.get_exit_ids())
        return ids

    def __and__(self, other: Node) -> "Parallel":
        return Parallel([*self.branches, other])

class Branch(Node):
    def __init__(self, decision_node: Node, paths: Dict[str, Node]):
        super().__init__(name="Branching")
        self.decision_node = decision_node
        self.paths = paths

    async def run(self, context: Optional[Dict[str, Any]] = None) -> Any:
        print(f"🌿 Evaluating Branch Condition: {self.decision_node.name}")
        # Run the decision node to get the choice (key)
        choice = await self.decision_node.run(context)
        print(f"👉 Branch Decision: '{choice}'")

        if choice in self.paths:
            print(f"🛣️ Taking path: {choice}")
            return await self.paths[choice].run(context)
        else:
            print(f"⚠️ No path found for '{choice}', skipping branch execution.")
            return choice

    def to_mermaid(self) -> str:
        # Render the decision node
        lines = [self.decision_node.to_mermaid()]

        # Render all path subgraphs/nodes
        for path_node in self.paths.values():
            lines.append(path_node.to_mermaid())

        # Create links from decision node exits to path entries with labels
        decision_exits = self.decision_node.get_exit_ids()

        for choice, path_node in self.paths.items():
            path_entries = path_node.get_entry_ids()
            for exit_id in decision_exits:
                for entry_id in path_entries:
                    # Mermaid link with label: A -- Label --> B
                    safe_choice = choice.replace('"', "'")
                    lines.append(f'{exit_id} -- "{safe_choice}" --> {entry_id}')

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "branch",
            "decision_node": self.decision_node.to_dict(),
            "paths": {k: v.to_dict() for k, v in self.paths.items()}
        }

    def get_entry_ids(self) -> List[str]:
        # Entry is the decision node
        return self.decision_node.get_entry_ids()

    def get_exit_ids(self) -> List[str]:
        # Exits are all the exits of the possible paths
        ids = []
        for path_node in self.paths.values():
            ids.extend(path_node.get_exit_ids())
        return ids

class HumanDecision(Node):
    def __init__(self, question: str, options: List[str] = ["yes", "no"]):
        super().__init__(name=f"Ask: {question}")
        self.question = question
        self.options = options

    async def run(self, context: Optional[Dict[str, Any]] = None) -> str:
        print(f"👤 USER INPUT REQUIRED: {self.question} {self.options}")
        # In a real implementation, this would pause/suspend
        return self.options[0]

    def to_mermaid(self) -> str:
        safe_name = self.name.replace('"', "'")
        return f'{self.id}{{"{safe_name}"}}:::human'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "human",
            "name": self.name,
            "question": self.question,
            "options": self.options
        }

    def get_entry_ids(self) -> List[str]:
        return [self.id]

    def get_exit_ids(self) -> List[str]:
        return [self.id]

# --- Agent System ---

class AgentArchetype:
    def __init__(self, role: str, skills: List[str]):
        self.role = role
        self.skills = skills

    def spawn(self, name: Optional[str] = None) -> "AgentInstance":
        instance_name = name or f"{self.role}-{str(uuid.uuid4())[:4]}"
        return AgentInstance(self, instance_name)

class AgentInstance:
    def __init__(self, archetype: AgentArchetype, name: str):
        self.archetype = archetype
        self.name = name
        self.memory: List[str] = []

    def task(self, instruction: str) -> Task:
        """Factory method to create a Task node for this agent."""
        return Task(self, instruction)

    async def do(self, instruction: str) -> str:
        """Simulate performing a task."""
        # This matches the previous implementation's simulation logic
        print(f"🤖 [{self.name}] Working on: {instruction}...")
        await asyncio.sleep(1) # Simulating IO/Work
        return f"Result of '{instruction}' by {self.name}"

# --- Execution Engine ---

class Runner:
    @staticmethod
    async def execute(node: Node, context: Optional[Dict[str, Any]] = None):
        print("🚀 Starting Flow Runner")
        try:
            result = await node.run(context or {})
            print("✅ Flow Completed Successfully")
            return result
        except Exception as e:
            print(f"❌ Flow Failed: {e}")
            raise

    @staticmethod
    def visualize(node: Node) -> str:
        header = ["graph TD",
                  "classDef task fill:#f9f,stroke:#333,stroke-width:2px;",
                  "classDef human fill:#ff9,stroke:#333,stroke-width:2px;"]
        body = node.to_mermaid()
        return "\n".join(header + [body])

    @staticmethod
    def to_json(node: Node) -> str:
        return json.dumps(node.to_dict(), indent=2)
