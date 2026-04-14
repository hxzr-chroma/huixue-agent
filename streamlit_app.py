"""
AI学习助手 - 主应用
"""
from __future__ import annotations

import json
import os
from datetime import date

import streamlit as st

from utils.auth_ui import show_auth_page
from utils.auth import get_user_by_id
from services.schedule import calendar_date_for_plan_day, parse_iso_date
from services.study_planner_service import StudyPlannerService
from storage.repository import StudyRepository
from utils.goal_validation import (
    FIELD_LABELS_ZH,
    goal_missing_fields_for_submission,
    merge_goal_supplements,
    validate_parsed_goal,
)

GOAL_CLARIFY_CREATE = "goal_clarify_create"
GOAL_CLARIFY_RECREATE = "goal_clarify_recreate"

NAV_ITEMS: list[tuple[str, str]] = [
    ("🏠 首页总览", "首页总览"),
    ("✨ 学习计划生成", "学习计划生成"),
    ("📋 当前学习计划", "当前学习计划"),
    ("📈 学习进度反馈", "学习进度反馈"),
    ("📝 学习检测", "学习检测"),
    ("🔄 动态调整", "动态调整"),
]


def initialize_app():
    """初始化应用配置"""
    st.set_page_config(
        page_title="AI 学习助手",
        page_icon="📘",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # 初始化session state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "current_plan_id" not in st.session_state:
        st.session_state.current_plan_id = None
    if "latest_generated_evaluation" not in st.session_state:
        st.session_state.latest_generated_evaluation = None


def check_login():
    """检查登录状态，如未登录则显示登录页面"""
    if not st.session_state.logged_in:
        show_auth_page()
        st.stop()


def inject_styles():
    """注入CSS样式"""
    st.markdown(
        """
        <style>
            .main .block-container {
                padding-top: 1.5rem;
                padding-bottom: 2rem;
                max-width: 920px;
            }
            .stApp {
                background: #f6f7f9;
            }
            [data-testid="stSidebar"] {
                background: #ffffff;
                border-right: 1px solid #e8eaed;
            }
            [data-testid="stSidebar"] .block-container {
                padding-top: 1.25rem;
            }
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_logout_button():
    """在侧边栏显示用户信息和登出按钮"""
    st.sidebar.divider()
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        st.sidebar.markdown(f"👤 **{st.session_state.username}**")
    with col2:
        if st.sidebar.button("退出", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.current_plan_id = None
            st.rerun()


def show_plan_selector():
    """在侧边栏显示计划选择器"""
    st.sidebar.markdown("### 📚 我的学习计划")
    
    repo = StudyRepository()
    plans = repo.get_user_plans(st.session_state.user_id)
    
    if not plans:
        st.sidebar.info("还没有学习计划，去生成一个吧！")
        return None
    
    # 创建计划选择列表
    plan_options = {}
    for plan in plans:
        plan_key = f"{plan['id']} | {plan.get('plan_name', '学习计划')}"
        plan_options[plan_key] = plan["id"]
    
    # 设置默认选中
    if st.session_state.current_plan_id is None and plans:
        st.session_state.current_plan_id = plans[0]["id"]
    
    current_key = None
    for key, pid in plan_options.items():
        if pid == st.session_state.current_plan_id:
            current_key = key
            break
    
    selected_key = st.sidebar.selectbox(
        "选择计划",
        list(plan_options.keys()),
        index=list(plan_options.values()).index(st.session_state.current_plan_id) if st.session_state.current_plan_id in plan_options.values() else 0,
        label_visibility="collapsed",
    )
    
    new_plan_id = plan_options[selected_key]
    if new_plan_id != st.session_state.current_plan_id:
        st.session_state.current_plan_id = new_plan_id
        st.rerun()
    
    # 显示当前计划信息
    current_plan = repo.get_plan_by_id(st.session_state.current_plan_id)
    return current_plan


def handle_goal_clarification_flow(service: StudyPlannerService, state_key: str):
    """目标补充流程"""
    pending = st.session_state.get(state_key)
    if not pending:
        return None, None

    parsed = pending["parsed_goal"]
    missing = goal_missing_fields_for_submission(pending["user_input"], parsed)

    if not missing:
        st.session_state.pop(state_key, None)
        with st.spinner("正在生成学习计划..."):
            try:
                plan, rag = service.create_plan(
                    pending["user_input"],
                    plan_start_date=pending["plan_start"],
                    parsed_goal=parsed,
                )
                # 保存计划名称
                plan_name = pending.get("plan_name", f"学习计划 {str(date.today())}")
                repo = StudyRepository()
                repo.update_plan_name(plan["id"], plan_name)
                return plan, rag
            except ValueError:
                return None, None

    st.warning("🧩 还缺几样信息～补全后就能生成计划啦。")
    
    with st.form(f"goal_clarify_{state_key}"):
        subject_val = duration_val = hours_val = topics_val = desc_val = None
        if "subject" in missing:
            subject_val = st.text_input(
                FIELD_LABELS_ZH["subject"],
                value=parsed.get("subject") or "",
            )
        if "duration_days" in missing:
            d0 = int(parsed.get("duration_days") or 7)
            d0 = max(1, min(365, d0))
            duration_val = st.number_input(
                FIELD_LABELS_ZH["duration_days"],
                min_value=1,
                max_value=365,
                value=d0,
                step=1,
            )
        if "daily_hours" in missing:
            h0 = float(parsed.get("daily_hours") or 2.0)
            h0 = max(0.5, min(24.0, h0))
            hours_val = st.number_input(
                FIELD_LABELS_ZH["daily_hours"],
                min_value=0.5,
                max_value=24.0,
                value=h0,
                step=0.5,
            )
        if "focus_topics" in missing:
            topics = parsed.get("focus_topics") or []
            topics_str = "、".join(topics) if topics else ""
            topics_val = st.text_area(
                FIELD_LABELS_ZH["focus_topics"],
                value=topics_str,
                height=100,
            )
        if "target_description" in missing:
            desc_val = st.text_area(
                FIELD_LABELS_ZH["target_description"],
                value=parsed.get("target_description") or "",
                height=80,
            )
        
        c1, c2 = st.columns(2)
        with c1:
            cancelled = st.form_submit_button("↩️ 取消", use_container_width=True)
        with c2:
            submitted = st.form_submit_button(
                "✅ 补全并生成计划", type="primary", use_container_width=True
            )

    if cancelled:
        st.session_state.pop(state_key, None)
        st.rerun()

    if submitted:
        kw = {}
        if "subject" in missing:
            kw["subject"] = subject_val
        if "duration_days" in missing and duration_val is not None:
            kw["duration_days"] = int(duration_val)
        if "daily_hours" in missing and hours_val is not None:
            kw["daily_hours"] = float(hours_val)
        if "focus_topics" in missing:
            kw["focus_topics_text"] = topics_val
        if "target_description" in missing:
            kw["target_description"] = desc_val
        merged = merge_goal_supplements(parsed, **kw)
        still = validate_parsed_goal(merged)
        if still:
            st.session_state[state_key]["parsed_goal"] = merged
            hint = "、".join(FIELD_LABELS_ZH[k] for k in still)
            st.error(f"以下信息仍不完整：{hint}")
            st.rerun()
        st.session_state.pop(state_key, None)
        with st.spinner("正在生成学习计划..."):
            try:
                plan, rag = service.create_plan(
                    pending["user_input"],
                    plan_start_date=pending["plan_start"],
                    parsed_goal=merged,
                )
                plan_name = pending.get("plan_name", f"学习计划 {str(date.today())}")
                repo = StudyRepository()
                repo.update_plan_name(plan["id"], plan_name)
                return plan, rag
            except ValueError:
                st.error("生成失败，请检查填写内容。")
                return None, None

    return None, None


def render_sidebar(service, current_plan):
    """渲染侧边栏菜单"""
    st.sidebar.markdown("### 📌 菜单")
    labels = [pair[0] for pair in NAV_ITEMS]
    picked = st.sidebar.radio(
        "页面",
        labels,
        label_visibility="collapsed",
    )
    page = dict(NAV_ITEMS)[picked]

    st.sidebar.divider()
    st.sidebar.caption("⏰ 今日")
    st.sidebar.markdown(f"**{date.today().isoformat()}**")
    if current_plan:
        snap = service.get_schedule_snapshot(current_plan["id"])
        if snap:
            st.sidebar.caption("📍 计划进度")
            st.sidebar.markdown(f"第 **{snap['current_plan_day']}** 天")

    return page


def render_plan(plan_record, schedule_snapshot=None):
    """渲染学习计划"""
    if not plan_record:
        st.info("📭 暂无计划，请先生成一个。")
        return

    plan_data = plan_record["plan_data"]
    
    st.markdown(f"### 📋 {plan_record.get('plan_name', '学习计划')}")
    
    if schedule_snapshot:
        st.caption(
            f"起始 **{schedule_snapshot['plan_start_date']}** · 第 **{schedule_snapshot['current_plan_day']}** / {schedule_snapshot['max_plan_day']} 天"
        )

    st.markdown("**摘要**")
    st.markdown(plan_data.get("summary", "暂无摘要"))

    c1, c2 = st.columns(2)
    with c1:
        with st.expander("🪜 阶段安排"):
            stages = plan_data.get("stages", [])
            if stages:
                for stage in stages:
                    st.markdown(f"**{stage.get('name', '阶段')}** · {stage.get('days', '待定')}")
            else:
                st.caption("暂无")

    with c2:
        with st.expander("🎯 里程碑"):
            milestones = plan_data.get("milestones", [])
            if milestones:
                for item in milestones:
                    st.write(f"· {item}")
            else:
                st.caption("暂无")

    st.markdown("**每日任务**")
    daily_tasks = plan_data.get("daily_tasks", [])
    if daily_tasks:
        for task in daily_tasks[:10]:  # 显示前10个
            day_n = task.get("day", "-")
            st.markdown(f"**Day {day_n}** · {task.get('task', '')} (~{task.get('estimated_hours', 0)}h)")
    else:
        st.caption("暂无每日任务。")


def show_rag_snippets(title: str, content: str | None):
    """折叠展示本次 RAG 检索到的知识片段。"""
    with st.expander(title, expanded=False):
        text = (content or "").strip()
        if text:
            st.markdown(text)
        else:
            st.caption("暂无命中片段。可在 `data/knowledge/` 添加 .md / .txt 后重试。")


def render_progress(service, current_plan):
    """学习进度反馈页面"""
    st.markdown("# 📈 学习进度反馈")
    st.markdown("记一笔今天学了多少，系统会顺手出反馈和小测题。")
    
    if not current_plan:
        st.info("请先生成计划。")
        return

    snap = service.get_schedule_snapshot(current_plan["id"])
    if snap:
        with st.expander("📌 今日对齐信息", expanded=False):
            st.caption(
                f"{snap['today_iso']} · 起始 {snap['plan_start_date']} · "
                f"计划第 **{snap['current_plan_day']}** 天"
            )
            if snap["today_tasks"]:
                for t in snap["today_tasks"]:
                    st.write(f"· Day {t.get('day')}：{t.get('task', '')}（~{t.get('estimated_hours', 0)}h）")
        if snap["needs_attention"]:
            st.warning("有缺勤或某天完成率低于 50%，可改日期补录或去「动态调整」。")

    col1, col2 = st.columns([1.1, 1])
    with col1:
        record_date = st.date_input(
            "📅 进度日期",
            value=date.today(),
            help="补录昨天请改选日期。",
        )
        completion_ratio = st.slider("✅ 当日完成度 (%)", 0, 100, 60)
        completed_tasks = st.text_area("✔️ 已完成", placeholder="今天搞定了什么")
        pending_tasks = st.text_area("⏳ 未完成", placeholder="还剩什么")
    with col2:
        delay_reason = st.text_input("🤔 偏差原因（可选）", placeholder="时间不够 / 其他课挤占…")
        note = st.text_area("💭 备注（可选）", height=160, placeholder="随手记两句")

    if st.button("📤 提交进度并生成反馈", type="primary", use_container_width=True):
        progress_data = {
            "study_date": record_date.isoformat(),
            "completion_ratio": completion_ratio,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "delay_reason": delay_reason,
            "note": note,
        }
        latest = service.record_progress(current_plan["id"], progress_data)
        generated_evaluation = service.generate_evaluation(current_plan["id"])
        st.session_state.latest_generated_evaluation = generated_evaluation
        if latest:
            st.success("📝 已记下～")
            with st.expander("📊 反馈详情", expanded=False):
                st.json(latest["feedback"])
            if generated_evaluation:
                show_rag_snippets(
                    "📚 出题参考（RAG）",
                    generated_evaluation.get("rag_context"),
                )
                st.info("🎯 检测题已备好，去「📝 学习检测」答题吧。")
        else:
            st.error("学习进度记录失败，请稍后重试。")


def render_evaluation(service, current_plan):
    """学习检测页面"""
    st.markdown("# 📝 学习检测")
    st.markdown("先记进度才会出题；答完保存结果。")
    
    if not current_plan:
        st.info("请先生成计划。")
        return

    latest_generated_evaluation = st.session_state.get("latest_generated_evaluation")
    latest_saved_evaluation = service.get_latest_evaluation(current_plan["id"])

    if latest_generated_evaluation:
        if latest_generated_evaluation.get("focus_summary"):
            st.caption(f"🎯 {latest_generated_evaluation.get('focus_summary', '')}")
        show_rag_snippets(
            "📚 出题参考（RAG）",
            latest_generated_evaluation.get("rag_context"),
        )
        st.markdown("**题目**")
        for question in latest_generated_evaluation.get("questions", []):
            st.markdown(
                f"""
                **{question.get('id', '-')} · {question.get('type', '题')}**
                
                {question.get('question', '')}
                
                考点：{question.get('check_point', '')}
                ---
                """
            )

        total_questions = len(latest_generated_evaluation.get("questions", []))
        score = st.number_input(
            "✅ 答对几题？",
            min_value=0,
            max_value=max(total_questions, 1),
            value=0,
            step=1,
        )
        user_answers = st.text_area("✏️ 答题简述（可选）", placeholder="一两句思路即可")
        evaluation_summary = st.text_area("🪞 自我总结（可选）", placeholder="哪里卡住了？")

        if st.button("💾 提交检测结果", type="primary", use_container_width=True):
            saved_evaluation = service.save_evaluation_result(
                current_plan["id"],
                score=score,
                total_questions=total_questions,
                user_answers=user_answers,
                summary=evaluation_summary,
                questions=latest_generated_evaluation.get("questions", []),
            )
            if saved_evaluation:
                st.success("🎉 已保存")
                with st.expander("📊 结果详情", expanded=False):
                    st.json(saved_evaluation)
    elif latest_saved_evaluation:
        st.success("📂 已有最近一次检测结果")
        with st.expander("📊 查看详情", expanded=False):
            st.json(latest_saved_evaluation)
    else:
        st.info("请先去「📈 学习进度反馈」提交一次进度。")


def render_adjustment(service, current_plan):
    """动态调整页面"""
    st.markdown("# 🔄 动态调整计划")
    st.markdown("结合进度、小测和日历，重排后面的任务。")
    
    if not current_plan:
        st.info("请先生成计划。")
        return

    snap = service.get_schedule_snapshot(current_plan["id"])
    if snap and snap["needs_attention"]:
        with st.expander("ℹ️ 关于缺勤时如何调整", expanded=False):
            st.caption(
                "有日历缺勤/未达标时，即使没有进度记录也可尝试调整；若有进度，会把日历摘要一并交给优化。"
            )

    st.caption("点按钮后，会刷新后续每日任务（原逻辑不变）。")
    if st.button("⚡ 生成调整建议", type="primary", use_container_width=True):
        result = service.adjust_plan(current_plan["id"])
        if not result:
            st.warning("需要先至少一条进度记录（或满足日历缺勤时的合成条件）。")
        else:
            st.success("✨ 已更新计划")
            with st.expander("📊 调整说明（JSON）", expanded=False):
                st.json(result["adjustment"])
            st.markdown("**调整后日程**")
            ns = service.get_schedule_snapshot(result["updated_plan"]["id"])
            render_plan(result["updated_plan"], ns)


# ========== 主程序 ==========
initialize_app()
check_login()

API_KEY = os.getenv("DEEPSEEK_API_KEY") or st.secrets.get("DEEPSEEK_API_KEY", "")
if not API_KEY:
    st.error("❌ 缺少 API 密钥")
    st.stop()

# 使用登录用户的ID初始化service
service = StudyPlannerService(api_key=API_KEY, user_id=st.session_state.user_id)

# 页面配置
inject_styles()

# 侧边栏：计划选择
current_plan = show_plan_selector()

# 侧边栏：菜单
page = render_sidebar(service, current_plan)

# 侧边栏：登出
show_logout_button()

# ========== 页面内容 ==========
if page == "首页总览":
    st.markdown("# 📘 AI 学习助手")
    st.markdown("智能学习规划与跟踪系统")
    
    if current_plan:
        st.success("✓ 已有活跃计划")
        render_plan(current_plan)
    else:
        st.info("还未创建学习计划，请去「学习计划生成」开始。")

elif page == "学习计划生成":
    st.markdown("# ✨ 生成新计划")
    st.markdown("描述你的学习目标，我来帮你制定详细的学习计划")
    
    with st.form("new_plan_form"):
        plan_name = st.text_input("计划名称（可选）", placeholder="如：雅思阅读突破")
        user_input = st.text_area(
            "学习目标",
            placeholder="例如：我要在12周内完成Python基础学习，每天3小时...",
            height=150,
        )
        plan_start = st.date_input("计划开始日期", value=date.today())
        
        if st.form_submit_button("🚀 生成计划", use_container_width=True, type="primary"):
            if not user_input.strip():
                st.error("请输入学习目标")
            else:
                with st.spinner("正在分析..."):
                    # 解析用户输入
                    parsed_goal = service.parse_user_goal(user_input)
                    
                    if parsed_goal:
                        st.session_state[GOAL_CLARIFY_CREATE] = {
                            "user_input": user_input,
                            "plan_start": str(plan_start),
                            "parsed_goal": parsed_goal,
                            "plan_name": plan_name or f"学习计划 {str(plan_start)}",
                        }
                        st.rerun()

    plan, rag = handle_goal_clarification_flow(service, GOAL_CLARIFY_CREATE)
    if plan:
        st.success("🎉 计划已创建！")
        st.balloons()
        st.rerun()

elif page == "当前学习计划":
    st.markdown("# 📋 当前学习计划")
    if current_plan:
        render_plan(current_plan)
    else:
        st.info("还未创建计划")

elif page == "学习进度反馈":
    render_progress(service, current_plan)

elif page == "学习检测":
    render_evaluation(service, current_plan)

elif page == "动态调整":
    render_adjustment(service, current_plan)
