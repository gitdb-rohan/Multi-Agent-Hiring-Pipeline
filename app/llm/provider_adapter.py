import json
import logging
from typing import Type, TypeVar, Any
from pydantic import BaseModel
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMProviderAdapter:
    """Abstract base class/interface for LLM providers."""
    async def generate_structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        model_name: str | None = None
    ) -> T:
        raise NotImplementedError

class OpenAIAdapter(LLMProviderAdapter):
    """OpenAI implementation of LLMProviderAdapter using structured outputs."""
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.default_model = "gpt-4o-mini"

    async def generate_structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        model_name: str | None = None
    ) -> T:
        model_to_use = model_name or self.default_model
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            completion = await self.client.beta.chat.completions.parse(
                model=model_to_use,
                messages=messages,
                response_format=response_model,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


class GeminiAdapter(LLMProviderAdapter):
    """Google Gemini implementation using the google-genai SDK."""

    def __init__(self):
        from google import genai
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.default_model = "gemini-3.1-flash-lite"

    async def generate_structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        model_name: str | None = None,
    ) -> T:
        import asyncio
        model_to_use = model_name or self.default_model

        full_prompt = ""
        if system_prompt:
            full_prompt += f"{system_prompt}\n\n"

        schema_json = json.dumps(response_model.model_json_schema(), indent=2)
        full_prompt += (
            f"USER REQUEST:\n{prompt}\n\n"
            f"Respond ONLY with valid JSON that exactly matches this JSON schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Return just the raw JSON object — no markdown fences, no explanation."
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=model_to_use,
                contents=full_prompt,
            )
        )

        raw_text = response.text.strip()
        # Strip any accidental markdown fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        data = json.loads(raw_text)
        return response_model(**data)


def get_llm_provider() -> LLMProviderAdapter:
    """Factory to get the configured LLM provider."""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        return OpenAIAdapter()
    if provider == "gemini":
        return GeminiAdapter()
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")

