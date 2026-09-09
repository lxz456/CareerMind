# CareerMind AI Career Plan Generation
#
# 单一入口：agents/career_planner_agent.py 和 api/career_plan.py 都调用 generate_career_plan()，
# 提示词只维护这一份。
from app.llm.llm_client import llm_json_call

CAREER_PLAN_SYSTEM_PROMPT = """你是资深职业教练和学习路径设计师。
根据技能差距分析，创建一份详细、可执行的职业发展计划。

只返回一个符合以下结构的有效 JSON 对象：
{
    "target_position": "用户输入的目标职位原文",
    "overview": "职业发展计划的简要概述",
    "total_months": 6,
    "key_milestones": [
        "第 3 个月：完成 Docker 与 Kubernetes 核心能力训练",
        "第 6 个月：具备参加目标岗位面试的能力"
    ],
    "plan": [
        {
            "month": 1,
            "theme": "夯实基础",
            "tasks": [
                {
                    "title": "学习 Docker 基础",
                    "description": "掌握容器、镜像、Dockerfile 与 Docker Compose",
                    "resources": [
                        {"name": "Docker 官方教程", "type": "documentation", "url": ""},
                        {"name": "Docker 实战课程", "type": "course", "url": ""}
                    ],
                    "estimated_hours": 40,
                    "project_idea": "将一个全栈应用容器化"
                }
            ],
            "expected_outcome": "能够构建并部署容器化应用"
        }
    ]
}

规则：
- 每个月应有明确主题
- 任务要具体、可执行，并给出预计小时数
- 包含动手实践的项目想法
- 资源应混合课程、书籍、文档
- 对时间投入要现实（假设每周 15-20 小时）
- 计划应循序渐进：每个月在前一个月基础上推进
- 包含用于跟踪进度的里程碑
- target_position 必须保留用户输入的原文
- overview、key_milestones、theme、title、description、project_idea、expected_outcome 必须使用简体中文
- 技术名称、产品名和资源原始名称可以保留英文；resources.type 保持 course、book、documentation、tutorial 或 paper"""

async def generate_career_plan(
    target_position: str,
    match_pct: float = 0,
    gaps: list[dict] | None = None,
) -> dict:
    """根据技能差距生成逐月的学习计划。"""
    gaps = gaps or []

    gap_descriptions = "\n".join(
        f"- {g.get('skill', '')}: current={g.get('current_level', 0)}, "
        f"required={g.get('required_level', 0)}, priority={g.get('priority', 'medium')}"
        for g in gaps
    ) or "- 无明确差距"

    user_prompt = f"""制定一份职业发展计划：

目标岗位：{target_position}
当前匹配度：{match_pct}%

技能差距：
{gap_descriptions}

设计一份逐月的学习计划，用以填补这些差距并为目标岗位做准备。"""

    result = await llm_json_call(
        system_prompt=CAREER_PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
        operation="career_plan",
    )

    return result
