# CareerMind AI Resume Parser
from app.llm.llm_client import llm_json_call

RESUME_PARSE_SYSTEM_PROMPT = """你是资深简历解析专家。从下面的简历文本中提取结构化信息。

只返回一个符合以下精确结构的有效 JSON 对象：
{
    "name": "full name or null",
    "summary": "short professional summary or null",
    "skills": ["skill1", "skill2", ...],
    "skill_levels": {"skill1": 4, "skill2": 5, ...},
    "experience": [
        {"company": "", "title": "", "duration": "", "description": ""}
    ],
    "education": [
        {"school": "", "degree": "", "major": "", "year": ""}
    ],
    "projects": [
        {"name": "", "description": "", "tech_stack": []}
    ],
    "overall_assessment": "用简体中文概括候选人的优势和待改进方向"
}

规则：
- 技能等级：1=初学者, 2=初级, 3=中级, 4=高级, 5=专家
- 只包含简历中实际存在的信息
- 要全面：提取所有提到的技能、技术、工具和框架
- summary、工作/项目描述和 overall_assessment 使用简体中文；姓名、公司、学校及技术专有名词保留原文"""

async def parse_resume_text(resume_text: str) -> dict:
    """用 LLM 解析简历文本，返回结构化数据。"""
    return await llm_json_call(
        system_prompt=RESUME_PARSE_SYSTEM_PROMPT,
        user_prompt=f"将下面的简历文本解析为结构化 JSON：\n\n---简历---\n{resume_text}\n---结束---",
        temperature=0.2,
        operation="resume_parse",
    )
