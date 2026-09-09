"""本地 BGE 精排模型适配器。"""

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any

from app.config import get_settings


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_model: Any | None = None
_tokenizer: Any | None = None
_device: str | None = None
_load_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _resolve_path(value: str) -> Path:
    """将相对路径固定解析到 backend 目录，避免启动目录改变缓存位置。"""
    path = Path(value)
    return path if path.is_absolute() else (_BACKEND_DIR / path).resolve()


def _load_reranker() -> tuple[Any, Any, str]:
    """首次调用时加载模型，之后在当前后端进程内复用同一实例。"""
    global _model, _tokenizer, _device
    if _model is not None and _tokenizer is not None and _device is not None:
        return _tokenizer, _model, _device

    with _load_lock:
        if _model is not None and _tokenizer is not None and _device is not None:
            return _tokenizer, _model, _device

        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        settings = get_settings()
        configured_device = settings.BGE_RERANK_DEVICE.lower().strip()
        if configured_device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif configured_device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("BGE_RERANK_DEVICE=cuda，但当前环境未检测到 CUDA")
        elif configured_device not in {"cpu", "cuda"}:
            raise ValueError("BGE_RERANK_DEVICE 仅支持 auto、cpu 或 cuda")
        else:
            device = configured_device

        model_dir = _resolve_path(settings.BGE_RERANK_MODEL_DIR)
        model_dir.mkdir(parents=True, exist_ok=True)
        # 已预下载时直接读本地目录；新环境中目录为空时按模型 ID 下载到同一目录。
        model_source = (
            str(model_dir)
            if (model_dir / "config.json").is_file()
            else settings.BGE_RERANK_MODEL
        )
        load_options: dict[str, Any] = {}
        if model_source == settings.BGE_RERANK_MODEL:
            load_options["cache_dir"] = str(model_dir)

        tokenizer = AutoTokenizer.from_pretrained(model_source, **load_options)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_source,
            **load_options,
        )
        model.eval()
        model.to(device)

        _tokenizer = tokenizer
        _model = model
        _device = device
        return tokenizer, model, device


def _compute_scores(query: str, documents: list[str]) -> list[float]:
    """分批计算 query-document 相关性，并用 sigmoid 映射到 0～1。"""
    import torch

    settings = get_settings()
    tokenizer, model, device = _load_reranker()
    scores: list[float] = []
    batch_size = max(1, settings.BGE_RERANK_BATCH_SIZE)

    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        pairs = [[query, document] for document in batch]
        inputs = tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=max(32, settings.BGE_RERANK_MAX_LENGTH),
        )
        inputs = {name: value.to(device) for name, value in inputs.items()}
        with torch.inference_mode():
            logits = model(**inputs, return_dict=True).logits.view(-1).float()
            scores.extend(torch.sigmoid(logits).cpu().tolist())

    return scores


async def rerank_documents(
    query: str,
    documents: list[str],
    top_n: int,
) -> list[dict]:
    """使用 BAAI/bge-reranker-v2-m3 精排，返回原始索引和相关性分数。"""
    if not documents:
        return []

    # PyTorch 推理是同步计算，放到工作线程避免阻塞 FastAPI 事件循环。
    settings = get_settings()
    started = time.perf_counter()
    try:
        scores = await asyncio.wait_for(
            asyncio.to_thread(_compute_scores, query, documents),
            timeout=settings.BGE_RERANK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "BGE rerank timed out candidates=%d timeout_seconds=%.1f",
            len(documents), settings.BGE_RERANK_TIMEOUT_SECONDS,
        )
        raise
    logger.info(
        "BGE rerank completed candidates=%d returned=%d duration_ms=%d device=%s",
        len(documents),
        min(max(top_n, 1), len(documents)),
        round((time.perf_counter() - started) * 1000),
        _device or settings.BGE_RERANK_DEVICE,
    )
    ranked_indices = sorted(
        range(len(scores)), key=lambda index: scores[index], reverse=True
    )[: min(max(top_n, 1), len(documents))]
    return [
        {"index": index, "score": float(scores[index])}
        for index in ranked_indices
    ]
