from models.models import SWEBenchTaskInput, MBPPTaskInput

def swe_user_prompt(task: SWEBenchTaskInput) -> str:
    prompt = (
        f"Fix the following GitHub issue in the repository `{task.repo}` "
        f"(Instance: `{task.instance_id}`), located inside `/testbed`.\n\n"
        f"### Problem Statement\n"
        f"{task.problem_statement}\n"
    )

    if task.hints_text and task.hints_text.strip():
        prompt += f"\n### Hints\n{task.hints_text.strip()}\n"

    prompt += (
        "\nExplore the repository in `/testbed` using your tools, implement a clean fix, "
        "verify it with `run_tests()`, and submit your patch with `final_answer(get_patch())`."
    )
    return prompt

def mbpp_user_prompt(task: MBPPTaskInput) -> str:
    prompt = (
        f"Solve the following Python task:"
        f"Task Description: {task.task_definition}"
        f"Required Function Signature: {task.function_definition}\n"
        f"Test Imports:"
        f"{task.test_imports}\n"
        f"Public Test Cases to Pass:"
        f"{task.test_list}"
    )
    return prompt

def swe_prompt(task: SWEBenchTaskInput):
    try:
        with open('llm/swe_system_prompt.txt', 'r') as file:
            system_prompt = file.read()
        return system_prompt, swe_user_prompt(task)

    except FileNotFoundError:
        print(f"File does not exist")
    except PermissionError:
        print(f"No permission to read")
    except Exception as e:
        print(e)

def mbpp_prompt(task: MBPPTaskInput):
    try:
        with open('llm/mbpp_system_prompt.txt', 'r') as file:
            system_prompt = file.read()
        return system_prompt, mbpp_user_prompt(task)
    except FileNotFoundError:
        print(f"File does not exist")
    except PermissionError:
        print(f"No permission to read")

    except Exception as e:
        print(e)
