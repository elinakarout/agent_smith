from typing import Any, NoReturn


class FinalAnswerSignal(Exception):
    pass


def final_answer(answer: Any) -> NoReturn:
    """Signal the final answer from inside the sandbox execution environment.

    Args:
        answer: The final result or answer object to return.

    Raises:
        FinalAnswerSignal: Always raised to convey the final answer to the executor.
    """
    raise FinalAnswerSignal(answer)
