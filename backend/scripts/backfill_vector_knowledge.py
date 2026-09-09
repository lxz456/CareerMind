"""从 SQLite 业务表补写 Chroma 知识索引。

用法（在 backend 目录执行）：
    python scripts/backfill_vector_knowledge.py --type resources
    python scripts/backfill_vector_knowledge.py --type questions
    python scripts/backfill_vector_knowledge.py --type all
"""
import argparse
import asyncio

from app.database import async_session
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from app.vector_store import (
    COLLECTION_QUESTIONS,
    COLLECTION_RESOURCES,
    get_vector_store,
)


async def _backfill(content_type: str) -> None:
    async with async_session() as db:
        if content_type in {"questions", "all"}:
            before = get_vector_store().count(COLLECTION_QUESTIONS)
            result = await KnowledgeIngestionService.reindex_questions(db)
            after = get_vector_store().count(COLLECTION_QUESTIONS)
            print(
                "questions: "
                f"sql={result.unique_count}, chroma_before={before}, "
                f"indexed={result.vector_indexed}, chroma_after={after}"
            )

        if content_type in {"resources", "all"}:
            before = get_vector_store().count(COLLECTION_RESOURCES)
            result = await KnowledgeIngestionService.reindex_resources(db)
            after = get_vector_store().count(COLLECTION_RESOURCES)
            print(
                "resources: "
                f"sql={result.unique_count}, chroma_before={before}, "
                f"indexed={result.vector_indexed}, chroma_after={after}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Chroma knowledge indexes")
    parser.add_argument(
        "--type",
        choices=("questions", "resources", "all"),
        default="all",
    )
    args = parser.parse_args()
    asyncio.run(_backfill(args.type))


if __name__ == "__main__":
    main()
