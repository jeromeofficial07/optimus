"""
Agent - builds and owns the agent components so they can be created in one line.
"""
from app.agent.controller import ExecutionController
from app.agent.executor import ToolExecutor
from app.agent.planner import TaskPlanner
from app.agent.verifier import ResultVerifier


class Agent:
    def __init__(self, executor: ToolExecutor, llm=None):
        self.permissions = executor.permissions
        self.verifier = ResultVerifier(executor.context)
        self.planner = TaskPlanner(executor.registry, executor.context.guard, llm)
        self.controller = ExecutionController(executor, self.verifier, self.planner)