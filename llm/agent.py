import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import (
    OpenAI,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
    APITimeoutError,
)

load_dotenv()

PROVIDERS = [
    {
        "name": "openrouter",
        "url": "https://openrouter.ai/api/v1",
        "key_prefix": "OPENROUTER_API_KEY",
        "model": "openrouter/free",
    },
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1",
        "key_prefix": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
    },
    {
        "name": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_prefix": "GEMINI_API_KEY",
        "model": "gemini-3.8-flash",
    },
]


@dataclass
class LLMSolution:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_time_ms: float = 0.0
    retries: int = 0
    url: str = ""
    model_name: str = ""
    answer: str = ""


class LLMClient:
    def __init__(self, model_name: str, url_provider: str, timeout_time: float = 60.0, max_tokens: int = 500):
        self.default_model = model_name
        self.default_url = url_provider.rstrip("/")
        self.timeout_time = timeout_time
        self.max_tokens = max_tokens
        self.stop_sequences = [
            "<end_code>",
            "</tool_call>",
            "</invoke>",
            "\nObservation:",
        ]

    def create_openai_client(self, api_key: str, base_url: str) -> OpenAI:
        return OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=self.timeout_time,
            max_retries=0
        )

    def get_keys_by_prefix(self, prefix: str) -> List[str]:
        """Load standard key (PREFIX) and numbered keys (PREFIX_1, PREFIX_2) from .env"""
        keys: List[str] = []
        exact_val = os.getenv(prefix)
        if exact_val:
            keys.extend([k.strip() for k in exact_val.split(",") if k.strip()])

        for env_name, env_val in sorted(os.environ.items()):
            if env_name.startswith(f"{prefix}_") and env_val:
                for k in env_val.split(","):
                    clean_k = k.strip()
                    if clean_k and clean_k not in keys:
                        keys.append(clean_k)
        return keys

    def get_keys_for_url(self, url: str) -> List[str]:
        """Match the best API keys for a custom provider URL before falling back to all keys."""
        url_lower = url.lower()
        if "openrouter" in url_lower:
            return self.get_keys_by_prefix("OPENROUTER_API_KEY")
        if "groq" in url_lower:
            return self.get_keys_by_prefix("GROQ_API_KEY")
        if "gemini" in url_lower:
            return self.get_keys_by_prefix("GEMINI_API_KEY")
        if "together" in url_lower:
            return self.get_keys_by_prefix("TOGETHER_API_KEY")
        if "mistral" in url_lower:
            return self.get_keys_by_prefix("MISTRAL_API_KEY")

        all_keys: List[str] = []
        for p in PROVIDERS:
            for k in self.get_keys_by_prefix(p["key_prefix"]):
                if k not in all_keys:
                    all_keys.append(k)
        return all_keys

    def chat(self, client: OpenAI, model_name: str, provider_url: str, messages: List[Dict[str, str]], retries: int) -> LLMSolution:
        start_time = time.perf_counter()

        response = client.chat.completions.create(model=model_name,
            messages=messages, max_tokens=self.max_tokens, temperature=0.0, stop=self.stop_sequences)

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        answer = response.choices[0].message.content
        usage = response.usage

        return LLMSolution(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            request_time_ms=elapsed_ms,
            retries=retries,
            url=provider_url,
            model_name=model_name,
            answer=answer,
        )

    def llm_asker(self, messages: List[Dict[str, str]]) -> LLMSolution:
        """
        Send a multi-turn conversation history to the primary provider/model,
        rotating API keys and falling back to secondary providers on failure.
        """
        errors: List[str] = []
        attempted = set()
        retries = 0

        custom_provider = {
            "name": "custom",
            "url": self.default_url,
            "model": self.default_model,
            "keys": self.get_keys_for_url(self.default_url),
        }

        fallback_providers = [
            {
                "name": p["name"],
                "url": p["url"].rstrip("/"),
                "model": p["model"],
                "keys": self.get_keys_by_prefix(p["key_prefix"]),
            }
            for p in PROVIDERS
        ]

        providers_to_try = [custom_provider] + fallback_providers

        for provider in providers_to_try:
            provider_name = provider["name"]
            provider_url = provider["url"]
            model_name = provider["model"]
            api_keys = provider["keys"]

            combination = (provider_url, model_name)
            if combination in attempted:
                continue
            attempted.add(combination)

            if not api_keys:
                errors.append(f"{provider_name}: No API keys configured")
                continue

            for key_index, api_key in enumerate(api_keys, start=1):
                try:
                    with self.create_openai_client(api_key, provider_url) as client:
                        return self.chat(
                            client=client,
                            model_name=model_name,
                            provider_url=provider_url,
                            messages=messages,
                            retries=retries,
                        )

                except RateLimitError as e:
                    retries += 1
                    errors.append(f"{provider_name} (key #{key_index}): Rate limit reached - {e}")
                    time.sleep(min(1.5**retries, 5.0))
                    continue

                except (APIConnectionError, APITimeoutError) as e:
                    retries += 1
                    errors.append(f"{provider_name} (key #{key_index}): Connection/Timeout error - {e}")
                    time.sleep(1.0)
                    continue

                except APIStatusError as e:
                    retries += 1
                    errors.append(f"{provider_name} (key #{key_index}): HTTP {e.status_code} - {e}")
                    # If the model name itself is invalid (400/404) on this provider,
                    # break out of the key loop and move to the next provider.
                    if e.status_code in (400, 404):
                        break
                    if e.status_code in (401, 402, 403, 408, 429, 500, 502, 503, 504):
                        continue
                    raise

                except Exception as e:
                    retries += 1
                    errors.append(f"{provider_name} (key #{key_index}): Unexpected error - {e}")
                    continue

        raise RuntimeError("All configured LLM providers and API keys failed:\n" + "\n".join(errors))
