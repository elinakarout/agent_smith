from models.models import MBPPTaskInput, SWEBenchTaskInput, StepMetrics, SolutionOutput
from sandbox.executor import SandboxExecutor, SandboxConfig
from llm.prompts import swe_prompt, mbpp_prompt
from typing import Dict, List, Optional
from sandbox.config import read_config
from dataclasses import dataclass
from llm.agent import LLMClient
from llm.extractor import extract_code
import textwrap
import json


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
    def __init__(self, type: str, task: MBPPTaskInput | SWEBenchTaskInput, model_name, api_url):
        self.benchmark = type
        self.task:MBPPTaskInput | SWEBenchTaskInput = task
        self.solution: SolutionOutput | None = None
        self.model_name = model_name
        self.api_url = api_url

    def answer(self):
        if (self.benchmark == "mbpp"):
            self.answermbpp()
        else:
            self.answerswe()

    def answermbpp(self):
        solution_dict = {
            "task_id": str(self.task.task_id),
            "benchmark": "mbpp",
            "success": False,
            "solution": "",
            "system_prompt": "",
            "iterations": 0,
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_time_seconds": 0.0,
            "steps": [],
            "error": None
        }
        config = SandboxConfig()
        executor = SandboxExecutor(config)
        curr_step = 1
        while True:
            client = LLMClient(self.model_name, self.api_url, MBPP_LIMITS.timeout_seconds, MBPP_LIMITS.max_input_tokens)
            system_prompt, mbpp_user_prompt = mbpp_prompt(self.task)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": mbpp_user_prompt},
            ]

            sol = client.llm_asker(messages)

            code, warning = extract_code(sol.answer or "")
            result = None
            if code is None:
                sandbox_output = warning or "Extraction failed"
            else:
                # [MCP]: Inject `run_tests` from `mcp_tools_mbpp.py` and detect
                # `final_answer(solution_code)` calls from the sandbox result
                result = executor.execute_code(code)
                sandbox_output = result.stdout

            step_metr = StepMetrics(
                step=curr_step,
                input_tokens=sol.input_tokens,
                output_tokens=sol.output_tokens,
                request_time_ms=sol.request_time_ms,
                api_url=sol.url,
                model_name=sol.model_name,
                llm_output=sol.answer or "",
                sandbox_input=code or "",
                sandbox_output=sandbox_output,
                retries=1
            )
            curr_step += 1
            solution_dict["iterations"] = curr_step
            solution_dict["total_requests"] += 1 + sol.retries
            solution_dict["total_input_tokens"] += step_metr.input_tokens
            solution_dict["total_output_tokens"] += step_metr.output_tokens
            solution_dict["total_time_seconds"] += (step_metr.request_time_ms / 1000)
            messages.append({"role": "user", "content": f"Observation:\n{sandbox_output}"})

            # [MCP]: Set `solution_dict["success"] = True` and `solution_dict["solution"] = final_answer_value`
            # once `final_answer(...)` is called inside the sandbox.

            solution_dict["steps"].append(step_metr)
            if step_metr.output_tokens >= MBPP_LIMITS.per_step_max_tokens:
                solution_dict["error"] = "Max output token exceeded"
                break
            if result is not None and result.status_code == "success":
                solution_dict["success"] = True
                solution_dict["solution"] = code
                break
            if solution_dict["iterations"] >= MBPP_LIMITS.max_iterations:
                solution_dict["error"] = "Max iterations exceeded"
                break
            if solution_dict["total_input_tokens"] >= MBPP_LIMITS.max_input_tokens:
                solution_dict["error"] = "Max input tokens exceeded"
                break
            if solution_dict["total_output_tokens"] >= MBPP_LIMITS.max_output_tokens:
                solution_dict["error"] = "Max output tokens exceeded"
                break
            if solution_dict["total_time_seconds"] >= MBPP_LIMITS.timeout_seconds:
                solution_dict["error"] = "Time exceeded"
                break

        solution_dict["system_prompt"] = system_prompt
        final_result = SolutionOutput(**solution_dict)
        if not final_result.error:
            final_result.error = "Worked perfectly"
        if not final_result.solution:
            final_result.solution = "No soltion"
        print(final_result.error)
        print(final_result.solution)
        print(len(final_result.steps))
        print(f'\n\n\n\n{final_result.success}')


    def answerswe(self):
        solution_dict = {
            "task_id": self.task.instance_id,
            "benchmark": "swebench",
            "success": False,
            "solution": "",
            "system_prompt": "",
            "iterations": 0,
            "total_requests": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_time_seconds": 0.0,
            "steps": [],
            "error": None,
        }

        # [MCP]: Inject dynamic MCP tool documentation / sandbox manual into system_prompt
        # once the MCP client lists tools from the SWE-bench MCP server.
        # Example:
        # mcp_manual = mcp_client.get_tools_manual()
        # system_prompt = f"{system_prompt}\n\n{mcp_manual}"

        # Start/connect the SWE-bench Docker environment and MCP server
        # (using self.task.docker_image and self.task.eval_script) before entering the loop.
        # Ensure cleanup (closing MCP session + removing Docker container) runs in a `finally:`.
        curr_step = 1
        try:
            while curr_step <= SWEBENCH_LIMITS.max_iterations:
                client = LLMClient(self.model_name, self.api_url, SWEBENCH_LIMITS.timeout_seconds, SWEBENCH_LIMITS.per_step_max_tokens)
                system_prompt, swe_user_prompt = swe_prompt(self.task)
                messages: List[Dict[str, str]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": swe_user_prompt},
                ]

                sol = client.llm_asker(messages)
                raw_llm_output = sol.answer or ""
                messages.append({"role": "assistant", "content": raw_llm_output})

                code, warning = extract_code(raw_llm_output)

                # [MCP]: When executing `code` in the sandbox, wire MCP tool calls
                # (read_file, edit_file, list_files, search_code,
                # search_function_or_class_definition_in_code, find_references,
                # run_tests, get_patch, run_command) to the SWE-bench MCP server.
                # Also detect if the sandboxed code invoked `final_answer(patch)` and capture.

                config = SandboxConfig()
                executor = SandboxExecutor(config)

                result = None
                if code is None:
                    sandbox_output = warning or "Extraction failed"
                else:
                    result = executor.execute_code(code)
                    stdout_text = getattr(result, "stdout", "") or ""
                    stderr_text = getattr(result, "stderr", "") or ""
                    combined_out = f"{stdout_text}\n{stderr_text}".strip()
                    sandbox_output = (f"{warning}\n{combined_out}".strip() if warning else combined_out)

                step_metr = StepMetrics(
                    step=curr_step,
                    input_tokens=sol.input_tokens,
                    output_tokens=sol.output_tokens,
                    request_time_ms=sol.request_time_ms,
                    api_url=sol.url,
                    model_name=sol.model_name,
                    llm_output=raw_llm_output,
                    sandbox_input=code or "",
                    sandbox_output=sandbox_output,
                    retries=sol.retries,
                )

                solution_dict["steps"].append(step_metr)
                solution_dict["iterations"] = curr_step
                solution_dict["total_requests"] += 1 + sol.retries
                solution_dict["total_input_tokens"] += step_metr.input_tokens
                solution_dict["total_output_tokens"] += step_metr.output_tokens
                solution_dict["total_time_seconds"] += step_metr.request_time_ms / 1000.0
                # Feed sandbox observation back into conversation history for the next iteration
                messages.append({"role": "user", "content": f"Observation:\n{sandbox_output}"})

                #  [MCP]: Mark `solution_dict["success"] = True` and store the patch from
                # `final_answer(get_patch())` in `solution_dict["solution"]` once submitted.
                if solution_dict["success"]:
                    break

                if solution_dict["iterations"] >= SWEBENCH_LIMITS.max_iterations:
                    solution_dict["error"] = "Max iterations exceeded"
                    break
                if solution_dict["total_input_tokens"] >= SWEBENCH_LIMITS.max_input_tokens:
                    solution_dict["error"] = "Max input tokens exceeded"
                    break
                if solution_dict["total_output_tokens"] >= SWEBENCH_LIMITS.max_output_tokens:
                    solution_dict["error"] = "Max output tokens exceeded"
                    break
                if solution_dict["total_time_seconds"] >= SWEBENCH_LIMITS.timeout_seconds:
                    solution_dict["error"] = "Time exceeded"
                    break

                curr_step += 1

        finally:
            # CLEAN up docker
            pass

        solution_dict["system_prompt"] = system_prompt
        self.solution = SolutionOutput(**solution_dict)
        return self.solution


if __name__ == "__main__":
    with open('/sgoinfre/mrammal/agent_git/moulinette/evaluations/mbpp/2026-03-01_13-12-36/282/task.json', 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 1. Validate and load the task into MBPPTaskInput
    task = MBPPTaskInput(**data)

    # 2. Initialize the Orchestrator
    orchestrator = Orchestrator(
        type="mbpp",
        task=task,
        model_name="qwen/qwen-2.5-coder-32b-instruct:free",
        api_url="https://openrouter.ai/api/v1",
    )

    # 3. Run the MBPP flow (using your current method name `asnwer`)
    orchestrator.answer()

