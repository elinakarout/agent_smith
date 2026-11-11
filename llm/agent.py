import os
from dotenv import load_dotenv
from openai import (
    OpenAI,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
)

load_dotenv()

PROVIDERS = [
    {
        "name": "openrouter",
        "url": "https://openrouter.ai/api/v1",
        "keys": [
            "OPENROUTER_API_KEY_2",
            "OPENROUTER_API_KEY_1",
        ],
        "model": "openrouter/free",
    },
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1",
        "keys": ["GROQ_API_KEY_1", "GROQ_API_KEY_2"],
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "keys": ["GEMINI_API_KEY"],
        "model": "gemini-3.8-flash",
    },
]


def create_llm_client(provider_url, api_key):
    return OpenAI(
        base_url=provider_url,
        api_key=api_key,
        timeout=60,
        max_retries=0,
    )


def chat(client, model_name, message):
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful AI assistant.",
            },
            {
                "role": "user",
                "content": message,
            },
        ],
    )

    answer = response.choices[0].message.content
    usage = response.usage

    if usage:
        print(f"Input tokens:  {usage.prompt_tokens}")
        print(f"Output tokens: {usage.completion_tokens}")
        print(f"Total tokens:  {usage.total_tokens}")

    return answer



def llm_asker(message: str):
    errors = []

    for provider in PROVIDERS:
        provider_name = provider["name"]
        provider_url = provider["url"]
        model_name = provider["model"]

        print(f"\nTrying provider: {provider_name}")

        api_keys = [os.getenv(key_name) for key_name in provider["keys"] if os.getenv(key_name)]

        if not api_keys:
            error = f"{provider_name}: No API keys configured"
            print(error)
            errors.append(error)
            continue

        for key_index, api_key in enumerate(api_keys, start=1):
            try:
                with create_llm_client(provider_url, api_key) as client:
                    print(f"{provider_url}: {api_key}")
                    answer = chat(client, model_name, message)
                print(f"Worked with: {provider_name} ({model_name})")
                return answer

            except RateLimitError as e:
                error = (f"{provider_name} key {key_index}: Rate limit reached - {e}")
                print(error)
                errors.append(error)
                continue

            except APIConnectionError as e:
                error = (
                    f"{provider_name} key {key_index}: "
                    f"Connection error - {e}"
                )
                print(error)
                errors.append(error)
                continue

            except APIStatusError as e:
                error = (f"{provider_name} key {key_index}: API error (HTTP {e.status_code}) - {e}")
                print(error)
                errors.append(error)

                if e.status_code in [401, 403, 402, 408, 429, 500, 502, 503, 504]:
                    continue
                raise

            except Exception as e:
                error = (f"{provider_name} key {key_index}: Unexpected error - {e}")
                print(error)
                errors.append(error)
                continue

    raise RuntimeError("All configured LLM providers and API keys failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    try:
        response = llm_asker("Very briefly explain why didn't momonuske open the land of Wano")
        print("\nFinal response:")
        print(response)

    except RuntimeError as e:
        print(f"\nLLM Error:\n{e}")
