# CareerMind AI Supervisor — Summary Node
"""
The supervisor acts as the final aggregation node in the career planning pipeline.
After all four agents complete (resume → job → gap → plan),
it stitches their outputs into a single readable summary.
"""
from app.agents.state import CareerPlanningState


async def supervisor_summary_node(state: CareerPlanningState) -> dict:
    """Generate a final summary from all agent outputs in the career planning pipeline.

    Called as the last node in: resume → job → skill_gap → career_plan → summary
    """
    resume = state.get("resume_data") or {}
    jobs = state.get("job_results") or []
    gaps = state.get("skill_gap_data") or {}
    plan = state.get("career_plan_data") or {}

    summary_parts = []

    # ---- Part 1: Resume Analysis ----
    if resume:
        name = resume.get("name") or state.get("user_id", "Candidate")
        skills = resume.get("skills", [])
        summary_parts.append(f"## 简历分析\n- 姓名: {name}\n- 技能: {', '.join(skills[:15])}")
        if resume.get("overall_assessment"):
            summary_parts.append(f"- 评估: {resume['overall_assessment']}")
        if state.get("target_position"):
            summary_parts.append(f"- 目标岗位: {state['target_position']}")

    # ---- Part 2: Job Matches ----
    if jobs:
        summary_parts.append(f"\n## 岗位搜索结果 (Top {min(3, len(jobs))})")
        for job in jobs[:3]:
            score_pct = round(job.get("score", 0) * 100)
            summary_parts.append(
                f"- **{job.get('title', 'N/A')}** @ {job.get('company', 'N/A')} "
                f"(相关度: {score_pct}%)\n  推荐理由: {job.get('reason', '')}"
            )

    # ---- Part 3: Skill Gaps ----
    if gaps:
        pct = gaps.get("match_percentage", 0)
        summary_parts.append(f"\n## 技能差距分析\n- 整体匹配度: {pct:.0f}%")
        for g in gaps.get("gaps", [])[:5]:
            summary_parts.append(
                f"- **{g.get('skill')}**: 当前 {g.get('current_level', 0)} → "
                f"要求 {g.get('required_level', 0)} (优先级: {g.get('priority', '中')})"
            )
        if gaps.get("recommendation"):
            summary_parts.append(f"- 建议: {gaps['recommendation']}")

    # ---- Part 4: Career Plan ----
    if plan:
        summary_parts.append(f"\n## 学习规划\n- 总时长: {plan.get('total_months', 0)} 个月")
        summary_parts.append(f"- 概述: {plan.get('overview', '')}")
        milestones = plan.get("key_milestones", [])
        if milestones:
            summary_parts.append("- 关键节点:")
            for m in milestones[:3]:
                summary_parts.append(f"  - {m}")

    summary = "\n".join(summary_parts) if summary_parts else "暂无分析结果"

    return {
        "final_summary": summary,
        "current_step": "completed",
        "completed_steps": ["summary"],
    }
