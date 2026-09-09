# CareerMind AI 内容清洗模块
#
# 职责：把 Tavily 搜到的学习资料网页，用 LLM 清洗成结构化资源卡片再入库。
#
# 岗位数据走 JSearch（本身就是结构化 JSON），由 tools/jsearch.py 做搜索编排，
# 不经过本模块清洗。
from app.llm.llm_client import llm_json_call

# ---- 学习资源清洗 ----
CLEAN_RESOURCES_SYSTEM_PROMPT = """你是从网页搜索结果中提取高质量学习资源的专家。

给定网页搜索结果，提取与技术职业发展相关的学习资源（课程、书籍、文档、教程）。

只返回一个有效的 JSON 对象：
{
    "resources": [
        {
            "name": "Resource title",
            "type": "course|book|documentation|tutorial|paper",
            "url": "https://...",
            "topic": "what it teaches, e.g. LangChain, Docker, RAG",
            "description": "1-2 sentence summary"
        }
    ]
}

规则：
- 优先知名、高质量来源（官方文档、有信誉的课程平台、大学资料）
- url 必须是搜索结果中的真实链接
- 忽略广告、论坛和低质内容
- 每个不同资源最多返回一条
- 不要编造内容中不存在的资源"""


async def clean_learning_resources(raw_results: list[dict]) -> list[dict]:
    """把 Tavily 原始结果清洗成学习资源卡片列表。"""
    if not raw_results:
        return []

    content_blocks = []
    for r in raw_results[:10]:
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")[:1500]
        if title or content:
            content_blocks.append(f"[来源] {title}\n[URL] {url}\n{content}")

    if not content_blocks:
        return []

    result = await llm_json_call(
        system_prompt=CLEAN_RESOURCES_SYSTEM_PROMPT,
        user_prompt=(
            "从这些搜索结果中提取学习资源：\n\n"
            + "\n\n---\n\n".join(content_blocks)
        ),
        temperature=0.2,
        operation="resource_cleaning",
    )
    return result.get("resources", [])
