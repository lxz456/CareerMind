# CareerMind AI Skill Gap Analysis
#
# 单一入口：agents/skill_gap_agent.py 和 api/skill_gap.py 都调用 analyze_skill_gap()，
# 提示词只维护这一份。
from app.llm.llm_client import llm_json_call

SKILL_GAP_SYSTEM_PROMPT = """你是资深技能分析专家。将用户当前技能与多个真实岗位的综合要求对比，识别共同能力差距。

只返回一个符合以下结构的有效 JSON 对象：
{
    "match_percentage": 75,
    "current_skills": [
        {"skill": "Python", "level": 4},
        {"skill": "PyTorch", "level": 3}
    ],
    "required_skills": [
        {"skill": "Python", "level": 5},
        {"skill": "PyTorch", "level": 4},
        {"skill": "Docker", "level": 3},
        {"skill": "Kubernetes", "level": 3}
    ],
    "gaps": [
        {
            "skill": "Docker",
            "current_level": 0,
            "required_level": 3,
            "priority": "high"
        }
    ],
    "recommendation": "针对上述差距给出具体、可执行的中文改进建议"
}

规则：
- match_percentage：按（匹配技能 / 所需技能总数）* 100 计算，并按重要性加权
- 综合所有提供的岗位要求；多个岗位重复出现的能力应提高优先级
- 不要只分析第一条岗位，也不要编造输入中没有依据的岗位要求
- 优先级："high" 为关键/核心技能，"medium" 为重要技能，"low" 为锦上添花
- 对差距要诚实且具体
- recommendation 必须使用简体中文；技能名和技术专有名词可以保留英文"""

async def analyze_skill_gap(
    user_skills: list[str],
    skill_levels: dict | None = None,
    job_title: str = "",
    job_requirements: list[str] | None = None,
) -> dict:
    """对比用户技能与目标岗位，返回技能差距分析 JSON。"""
    skill_levels = skill_levels or {}
    job_requirements = job_requirements or []

    user_prompt = f"""对比以下内容：

用户技能：
{user_skills}
技能等级：{skill_levels}

目标岗位：{job_title}
岗位要求：
{job_requirements}

分析用户与该目标岗位之间的技能差距。"""

    result = await llm_json_call(
        system_prompt=SKILL_GAP_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        operation="skill_gap",
    )
    return result
