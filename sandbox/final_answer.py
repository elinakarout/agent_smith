class FinalAnswerSignal(Exception):
    pass


def final_answer(answer):
    raise FinalAnswerSignal(answer)
