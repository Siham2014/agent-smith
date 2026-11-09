"""Concise code-generation and observation-driven correction prompts."""


def build_prompt(task: str, previous_code: str = "", observation: str = "") -> str:
    prompt = "Return Python code only. Do not execute code or claim it was tested.\nTask:\n" + task
    if observation:
        prompt += "\nCorrect the previous proposal using the static observation.\nPrevious code:\n" + previous_code
        prompt += "\nStatic observation:\n" + observation
    return prompt
