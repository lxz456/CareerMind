"""岗位检索词转换和真实岗位候选集排序的纯 LLM 能力。"""
import re

from app.llm.llm_client import llm_json_call


_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


JOB_QUERY_TRANSLATION_PROMPT = """你是职位搜索关键词翻译器。
把用户输入的中文目标职位转换为适合国际招聘搜索引擎使用的简洁英文职位名称。

只返回以下 JSON：
{
    "query": "English job title"
}

规则：
- 只翻译职位名称，不添加国家、城市、公司或用户没有提供的资历级别
- Java、Python、LLM、AI、RAG 等技术名词和缩写保持准确
- query 必须是简洁的英文招聘关键词，不要解释"""


async def normalize_job_search_query(target_position: str) -> str:
    """中文职位转成英文检索词；英文职位不额外调用模型。"""
    source = target_position.strip()
    if not source or not _CJK_PATTERN.search(source):
        return source

    result = await llm_json_call(
        system_prompt=JOB_QUERY_TRANSLATION_PROMPT,
        user_prompt=f"目标职位：{source}",
        temperature=0,
        operation="job_query_translation",
    )
    query = str(result.get("query", "")).strip()
    if not query or _CJK_PATTERN.search(query):
        raise ValueError("目标职位未能转换为有效的英文 JSearch 检索词")
    return query


JOB_RANK_SYSTEM_PROMPT = """你是岗位检索结果筛选专家。给定真实职位列表和用户条件，按相关性对它们排序。

只返回一个有效的 JSON 对象：
{
    "jobs": [
        {
            "candidate_index": 0,
            "score": 0.85,
            "reason": "该岗位与用户目标相符的中文理由"
        }
    ]
}

规则：
- score 0-1，越高匹配越好
- candidate_index 必须来自提供的候选编号，不得编造或重复
- 按 score 降序排列
- 有用户技能时，reason 应引用真实技能；没有用户技能时，按目标岗位、地点和岗位要求说明相关性
- reason 必须使用简体中文；技术名词、公司名和职位名可以保留原文"""


async def rank_jobs(
    candidates: list[dict],
    target_position: str,
    user_skills: list[str],
    top_k: int,
    location_label: str = "",
    job_requirements: str | None = None,
) -> dict:
    """使用 LLM 对工具层提供的真实岗位候选进行相关性排序。"""
    skills = ", ".join(user_skills) if user_skills else "Not specified"
    criteria = []
    if job_requirements:
        criteria.append(f"JOB REQUIREMENTS FILTER: {job_requirements}")
    if location_label:
        criteria.append(f"PREFERRED LOCATION: {location_label}")

    candidate_lines = []
    for index, candidate in enumerate(candidates):
        metadata = candidate.get("metadata", {})
        candidate_lines.append(
            f"- 候选编号 {index}: {metadata.get('title', '')} @ {metadata.get('company', '')} "
            f"({metadata.get('location', '')}) | 薪资: {metadata.get('salary_range', '')}\n"
            f"  描述: {candidate.get('document', '')[:500]}"
        )

    user_prompt = f"""请对以下真实岗位进行相关性排序：

目标职位：{target_position}
用户技能：{skills}
{chr(10).join(criteria)}
需要结果数：前 {top_k} 条

候选岗位：
{chr(10).join(candidate_lines)}

为每个岗位给出 0 到 1 的分数，并返回前 {top_k} 条。"""

    result = await llm_json_call(
        system_prompt=JOB_RANK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        operation="job_rank",
    )

    jobs = []
    seen_indexes = set()
    for ranked in result.get("jobs", []):
        try:
            index = int(ranked.get("candidate_index"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(candidates) or index in seen_indexes:
            continue
        seen_indexes.add(index)
        metadata = candidates[index].get("metadata", {})
        try:
            score = min(max(float(ranked.get("score", 0)), 0.0), 1.0)
        except (TypeError, ValueError):
            score = 0.0
        jobs.append({
            "job_id": metadata.get("job_id", ""),
            "title": metadata.get("title", ""),
            "company": metadata.get("company", ""),
            "location": metadata.get("location", ""),
            "salary_range": metadata.get("salary_range", ""),
            "requirements": metadata.get("requirements", []) or [],
            "description": metadata.get("description", ""),
            "source_url": metadata.get("source_url", ""),
            "score": score,
            "reason": str(ranked.get("reason", "")).strip(),
        })
        if len(jobs) >= top_k:
            break

    return {"jobs": jobs}
