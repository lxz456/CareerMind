"""Reusable interview tools for deterministic graphs and future agents."""
import logging
import re
import uuid

from app.config import get_settings
from app.llm.interview_questions import generate_questions_by_llm
from app.repositories.vector_knowledge_repo import VectorKnowledgeRepo


TYPE_TO_CATEGORY = {
    "hr": "behavioral",
    "technical": "technical",
    "system_design": "system_design",
    "mixed": None,
}
logger = logging.getLogger(__name__)
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _normalize_question(value: str) -> str:
    return "".join(str(value).lower().split())


def _is_excluded(candidate: str, excluded_questions: list[str]) -> bool:
    normalized = _normalize_question(candidate.split("\n", 1)[0])
    return any(
        normalized == _normalize_question(question)
        for question in excluded_questions
        if question
    )


def _assign_runtime_ids(questions: list[dict]) -> list[dict]:
    for index, question in enumerate(questions, start=1):
        question["question_id"] = str(uuid.uuid4())
        question["question_number"] = index
    return questions


def _question_from_candidate(candidate: dict) -> dict:
    """把最高分 Chroma 命中项转换为运行时题目，不再调用 LLM 二次选择。"""
    metadata = candidate.get("metadata") or {}
    document = str(candidate.get("document", ""))
    lines = [line.strip() for line in document.splitlines() if line.strip()]
    question = str(metadata.get("question") or (lines[0] if lines else "")).strip()

    expected_points: list[str] = []
    for line in lines[1:]:
        if line.startswith("考察点:") or line.startswith("考察点："):
            value = re.sub(r"^考察点[:：]\s*", "", line)
            expected_points = [
                point.strip()
                for point in re.split(r"[,，;；]", value)
                if point.strip()
            ]
            break

    return {
        "question": question,
        "category": metadata.get("category") or "general",
        "difficulty": metadata.get("difficulty") or "medium",
        "topic": metadata.get("topic") or "",
        "expected_points": expected_points,
    }


async def generate_questions(
    interview_type: str,
    target_position: str,
    difficulty: str = "medium",
    question_count: int = 5,
    skills: list[str] | None = None,
    question_mode: str = "review",
    question_index: int = 0,
    exclude_questions: list[str] | None = None,
) -> list[dict]:
    """按复习/进阶模式编排 RAG 检索、LLM 出题和向量缓存。"""
    skills = skills or []
    exclude_questions = exclude_questions or []
    generation_type = interview_type
    if interview_type == "mixed" and question_count == 1:
        generation_type = ("hr", "technical", "system_design")[question_index % 3]

    selected = []
    if question_mode == "review":
        query = " ".join([
            target_position,
            generation_type,
            difficulty,
            "interview questions",
            " ".join(skills),
        ]).strip()
        try:
            candidates = await VectorKnowledgeRepo.search_questions(
                query,
                top_k=max(question_count * 3, question_count),
                category=TYPE_TO_CATEGORY.get(generation_type),
                difficulty=difficulty,
            )
            candidates = [
                candidate
                for candidate in candidates
                if float(candidate.get("score", 0))
                >= get_settings().INTERVIEW_RAG_MIN_SCORE
                and _CJK_PATTERN.search(
                    str((candidate.get("metadata") or {}).get("question") or candidate.get("document", ""))
                )
                and not _is_excluded(
                    candidate.get("document", ""), exclude_questions
                )
            ]
        except Exception as exc:
            candidates = []
            logger.warning("Interview question cache search failed: %s", exc)

        if candidates:
            # Chroma 已按语义相似度降序返回；命中阈值后直接采用 Top-N，
            # 避免再调用一次 LLM 做候选选择。旧英文题会被过滤并走中文生成兜底。
            selected = [
                _question_from_candidate(candidate)
                for candidate in candidates[:question_count]
            ]

    selected = selected[:question_count]
    missing = question_count - len(selected)
    if missing:
        generated = await generate_questions_by_llm(
            generation_type,
            target_position,
            skills,
            missing,
            difficulty=difficulty,
            exclude_questions=exclude_questions + [
                item.get("question", "") for item in selected
            ],
        )
        selected.extend(generated[:missing])

    if not selected:
        raise ValueError("大模型未能生成可用的面试题")
    questions = selected[:question_count]
    for question in questions:
        # The graph's adaptive decision is authoritative, even if an older RAG
        # item or an LLM response contains a different difficulty label.
        question["difficulty"] = difficulty
    return _assign_runtime_ids(questions)
