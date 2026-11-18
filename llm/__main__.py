from .agent import LLMClient

try:
    client = LLMClient(
        model_name="qwen/qwen-2.5-coder-32b-instruct:free",
        url_provider="https://openrouter.ai/api/v1",
        max_tokens=1000,
    )

    messages = [
        {"role": "system", "content": "You are a tool to answer question"},
        {"role": "user", "content": "why didnt Momonuske open the land of wano?"},
    ]

    sol = client.llm_asker(messages)
    print(sol.answer)
    # sol.input_tokens, sol.output_tokens, sol.request_time_ms, sol.retries,
    # sol.url, sol.model_name, and sol.answer map directly to StepMetrics!
except Exception as e:
    print(e)

