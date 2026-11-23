from models.models import MBPPTaskInput, SWEBenchTaskInput, StepMetrics, SolutionOutput
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class AgentLimits:
    max_iterations: int
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: float
    per_step_max_tokens: int

MBPP_LIMITS = AgentLimits(
    max_iterations=10,
    max_input_tokens=6_000,
    max_output_tokens=1_500,
    timeout_seconds=120.0,
    per_step_max_tokens=450,
)

SWEBENCH_LIMITS = AgentLimits(
    max_iterations=30,
    max_input_tokens=300_000,
    max_output_tokens=10_000,
    timeout_seconds=900.0,
    per_step_max_tokens=1_500,
)

class Orchestrator():
    def __init__(self, type: str, task: MBPPTaskInput | SWEBenchTaskInput):
        self.benchmark = type
        self.task:MBPPTaskInput = task
        self.solution: SolutionOutput | None = None

    def asnwer(self):
        if (self.benchmark == "mbpp"):
            self.answermbpp()
        else:
            self.answerswe()

    def answermbpp(self):
        self.solution = SolutionOutput(task_id=self.task.task_id, benchmark="bmpp")




    def answerswe(self):
        self.solution = SolutionOutput(task_id=self.task.task_id, benchmark="swebench")