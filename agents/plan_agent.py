from utils.llm import LLMClient
from utils.json_parser import parse_json_response


class PlanAgent:

    def __init__(self, api_key):
        self.llm = LLMClient(api_key)

    def generate_plan(self, parsed_goal, rag_context=None):
        rag_block = ""
        if rag_context:
            rag_block = f"""

以下是从本地知识库检索到的参考片段（RAG）。请优先结合与用户目标相关的片段制定计划；若片段无关可忽略：
{rag_context}
"""
        
        # 从 parsed_goal 中提取关键信息
        subject = parsed_goal.get("subject", "")
        duration_days = parsed_goal.get("duration_days")
        daily_hours = parsed_goal.get("daily_hours")
        focus_topics = parsed_goal.get("focus_topics", [])
        target_desc = parsed_goal.get("target_description", "")
        
        # 构建清晰的目标说明
        goal_summary = f"学习主题：{subject}\n"
        if duration_days:
            goal_summary += f"学习周期：{duration_days} 天\n"
        if daily_hours:
            goal_summary += f"每日投入：{daily_hours} 小时\n"
        if focus_topics:
            goal_summary += f"重点内容：{', '.join(focus_topics)}\n"
        if target_desc:
            goal_summary += f"目标描述：{target_desc}\n"

        prompt = f"""
你是一名严谨的学习规划专家。

根据以下学习目标生成学习计划。

学习目标：
{goal_summary}
{rag_block}

【强制要求 - 必须完全遵守】
1. daily_tasks 数组必须有 {duration_days} 个元素，代表 {duration_days} 天的完整计划
2. 每个任务的 day 字段必须从 1 到 {duration_days}，连续递增
3. 每个任务的 estimated_hours 必须设置为 {daily_hours if daily_hours else "2"}
4. summary 字段必须明确说明"这是一个为期 {duration_days} 天的学习计划"
5. 不允许生成少于 {duration_days} 天的计划

【JSON 格式要求】
请输出完整的有效JSON，包含所有 {duration_days} 天的任务：
{{
  "summary": "这是一个为期 {duration_days} 天的 {subject} 学习计划，每天投入 {daily_hours if daily_hours else '2'} 小时。[详细说明]",
  "stages": [
    {{
      "name": "阶段名称",
      "days": "第X-Y天",
      "focus": ["重点主题"]
    }}
  ],
  "daily_tasks": [
    {", ".join([f'{{"day": {i}, "task": "第{i}天的学习任务", "estimated_hours": {daily_hours if daily_hours else "2"}}}' for i in range(1, min(6, (duration_days or 7) + 1))])}
    ...（共 {duration_days} 个任务）
  ],
  "milestones": ["里程碑1", "里程碑2"]
}}
"""

        raw_result = self.llm.chat(prompt)
        fallback = {
            "summary": "已根据目标生成基础学习计划。",
            "stages": [],
            "daily_tasks": [],
            "milestones": [],
        }
        result = parse_json_response(raw_result, fallback)
        
        # 验证和修正：如果生成的任务数不符合要求，进行调整
        if duration_days and isinstance(result.get("daily_tasks"), list):
            current_task_count = len(result["daily_tasks"])
            if current_task_count < duration_days:
                # 补全缺失的天数
                for day in range(current_task_count + 1, duration_days + 1):
                    result["daily_tasks"].append({
                        "day": day,
                        "task": f"第 {day} 天的学习任务",
                        "estimated_hours": daily_hours if daily_hours else 2
                    })
            elif current_task_count > duration_days:
                # 截断多余的天数
                result["daily_tasks"] = result["daily_tasks"][:duration_days]

        return result