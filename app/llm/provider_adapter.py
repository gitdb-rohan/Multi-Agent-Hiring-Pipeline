import json
import logging
import asyncio
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
        # Not using a global semaphore here. Celery worker thread limits should manage concurrency.

    async def generate_structured_output(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        model_name: str | None = None,
    ) -> T:
        from google.genai import types
        
        model_to_use = model_name or self.default_model
        
        full_prompt = ""
        if system_prompt:
            full_prompt += f"{system_prompt}\n\n"
        full_prompt += f"USER REQUEST:\n{prompt}"

        # Use native structured outputs
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
        )

        response = await self.client.aio.models.generate_content(
            model=model_to_use,
            contents=full_prompt,
            config=config,
        )

        raw_text = response.text.strip()
        data = json.loads(raw_text)
        return response_model(**data)

# Singleton instances
_OPENAI_ADAPTER = None
_GEMINI_ADAPTER = None

def get_llm_provider() -> LLMProviderAdapter:
    """Factory to get the configured LLM provider (Singleton)."""
    global _OPENAI_ADAPTER, _GEMINI_ADAPTER
    
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        if _OPENAI_ADAPTER is None:
            _OPENAI_ADAPTER = OpenAIAdapter()
        return _OPENAI_ADAPTER
    if provider == "gemini":
        if _GEMINI_ADAPTER is None:
            _GEMINI_ADAPTER = GeminiAdapter()
        return _GEMINI_ADAPTER
        
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")
