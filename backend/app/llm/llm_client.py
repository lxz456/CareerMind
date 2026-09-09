"""Shared LLM client, timeout handling, and diagnostic logging."""

import asyncio
import json
import logging
import time
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> BaseChatModel:
    """Create the DashScope OpenAI-compatible chat model."""
    common = {
        "temperature": temperature if temperature is not None else settings.LLM_TEMPERATURE,
        "timeout": settings.LLM_TIMEOUT_SECONDS,
        "max_retries": settings.LLM_MAX_RETRIES,
    }
    return ChatOpenAI(
        model=model or settings.DASHSCOPE_MODEL,
        openai_api_key=settings.DASHSCOPE_API_KEY,
        openai_api_base=settings.DASHSCOPE_BASE_URL,
        extra_body={"enable_thinking": settings.LLM_ENABLE_THINKING},
        **common,
    )


async def _invoke(llm: BaseChatModel, messages: list, operation: str):
    """Invoke a model with one total deadline and consistent diagnostic logs."""
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    started = time.perf_counter()
    logger.info("LLM call started operation=%s model=%s", operation, model_name)
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=settings.LLM_OPERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        duration_ms = round((time.perf_counter() - started) * 1000)
        logger.exception(
            "LLM call timed out operation=%s model=%s duration_ms=%d",
            operation, model_name, duration_ms,
        )
        raise
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000)
        logger.exception(
            "LLM call failed operation=%s model=%s duration_ms=%d",
            operation, model_name, duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000)
    usage = getattr(response, "usage_metadata", None) or {}
    if not usage:
        response_metadata = getattr(response, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or {}
    logger.info(
        "LLM call completed operation=%s model=%s duration_ms=%d "
        "input_tokens=%s output_tokens=%s total_tokens=%s",
        operation, model_name, duration_ms,
        usage.get("input_tokens", usage.get("prompt_tokens", "-")),
        usage.get("output_tokens", usage.get("completion_tokens", "-")),
        usage.get("total_tokens", "-"),
    )
    return response


async def llm_json_call(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    operation: str = "json_generation",
) -> dict:
    """Call the LLM and parse its response as a JSON object."""
    llm = get_llm(model=model, temperature=temperature)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    response = await _invoke(llm, messages, operation)
    content = response.content.strip()

    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.exception("LLM JSON parsing failed operation=%s", operation)
        raise


async def llm_text_call(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    operation: str = "text_generation",
) -> str:
    """Call the LLM and return plain text."""
    llm = get_llm(model=model, temperature=temperature)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    response = await _invoke(llm, messages, operation)
    return response.content.strip()
