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
from storage.db import init_db
from utils.goal_validation import (
    FIELD_LABELS_ZH,
    goal_missing_fields_for_submission,
    merge_goal_supplements,
    validate_parsed_goal,
)

GOAL_CLARIFY_CREATE = "goal_clarify_create"
GOAL_CLARIFY_RECREATE = "goal_clarify_recreate"

# 初始化数据库（使用缓存确保只执行一次）
@st.cache_resource
def init_database():
    init_db()

NAV_ITEMS: list[tuple[str, str]] = [
    ("🏠 首页总览", "首页总览"),
    ("✨ 学习计划生成", "学习计划生成"),
    ("📋 学习计划与进度", "学习计划与进度"),
    ("📝 学习检测", "学习检测"),
]


def initialize_app():
    """初始化应用配置"""
    st.set_page_config(
        page_title="AI 学习助手",
        page_icon="📘",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # 初始化数据库
    init_database()
    
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


def get_checkin_status(current_plan):
    """获取打卡状态"""
    if not current_plan:
        return None, False
    repo = StudyRepository()
    today_str = str(date.today())
    checkin = repo.get_daily_checkin(current_plan["id"], today_str)
    is_checked = checkin and checkin.get("is_checked_in", False)
    return repo, is_checked


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
    """目标补充流程 - 显示已提供和未提供的信息"""
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
                plan_name = pending.get("plan_name", f"学习计划 {str(date.today())}")
                repo = StudyRepository()
                repo.update_plan_name(plan["id"], plan_name)
                return plan, rag
            except ValueError:
                return None, None

    # 显示已提供和未提供的信息
    st.warning("🧩 还缺几样信息～补全后就能生成计划啦。")
    
    st.markdown("### ✅ 你已提供的信息")
    all_fields = ["subject", "duration_days", "daily_hours", "focus_topics", "target_description"]
    provided_count = 0
    for field in all_fields:
        if field not in missing:
            label = FIELD_LABELS_ZH.get(field, field)
            value = parsed.get(field, "")
            if isinstance(value, list):
                value = "、".join(value) if value else ""
            st.markdown(f"**{label}：** {value}")
            provided_count += 1
    
    if provided_count == 0:
        st.caption("暂无已提供的信息")
    
    st.markdown("### ⚠️ 需要补全的信息")
    
    with st.form(f"goal_clarify_{state_key}"):
        subject_val = duration_val = hours_val = topics_val = desc_val = None
        
        if "subject" in missing:
            st.markdown(f"**{FIELD_LABELS_ZH['subject']}** _(灰色表示未提供)_")
            subject_val = st.text_input(
                "输入学科",
                value=parsed.get("subject") or "",
                placeholder="例：Python基础",
                label_visibility="collapsed",
            )
        
        if "duration_days" in missing:
            st.markdown(f"**{FIELD_LABELS_ZH['duration_days']}** _(灰色表示未提供)_")
            d0 = int(parsed.get("duration_days") or 7)
            d0 = max(1, min(365, d0))
            duration_val = st.number_input(
                "输入天数",
                min_value=1,
                max_value=365,
                value=d0,
                step=1,
                label_visibility="collapsed",
                help="学习周期，单位为天（1-365天）",
            )
        
        if "daily_hours" in missing:
            st.markdown(f"**{FIELD_LABELS_ZH['daily_hours']}** _(灰色表示未提供)_")
            h0 = float(parsed.get("daily_hours") or 2.0)
            h0 = max(0.5, min(24.0, h0))
            hours_val = st.number_input(
                "输入小时数",
                min_value=0.5,
                max_value=24.0,
                value=h0,
                step=0.5,
                label_visibility="collapsed",
                help="每天学习时数（0.5-24小时）",
            )
        
        if "focus_topics" in missing:
            st.markdown(f"**{FIELD_LABELS_ZH['focus_topics']}** _(灰色表示未提供)_")
            topics = parsed.get("focus_topics") or []
            topics_str = "、".join(topics) if topics else ""
            topics_val = st.text_area(
                "输入重点科目",
                value=topics_str,
                height=80,
                label_visibility="collapsed",
                placeholder="例：数据结构、算法、系统设计（用「、」分隔）",
            )
        
        if "target_description" in missing:
            st.markdown(f"**{FIELD_LABELS_ZH['target_description']}** _(灰色表示未提供)_")
            desc_val = st.text_area(
                "输入学习目标",
                value=parsed.get("target_description") or "",
                height=80,
                label_visibility="collapsed",
                placeholder="例：完成3个实战项目，能独立开发应用",
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
    """渲染侧边栏 - 包含计划选择、今日规划、菜单、打卡"""
    # 1. 计划选择及管理
    st.sidebar.markdown("### 📚 我的学习计划")
    repo = StudyRepository()
    plans = repo.get_user_plans(st.session_state.user_id)
    
    if plans:
        plan_options = {}
        for plan in plans:
            plan_key = f"{plan['id']} | {plan.get('plan_name', '学习计划')}"
            plan_options[plan_key] = plan["id"]
        
        if st.session_state.current_plan_id is None and plans:
            st.session_state.current_plan_id = plans[0]["id"]
        
        try:
            current_idx = list(plan_options.values()).index(st.session_state.current_plan_id)
        except (ValueError, IndexError):
            current_idx = 0
        
        # 计划选择下拉框及删除按钮
        col1, col2 = st.sidebar.columns([5, 1])
        with col1:
            selected_key = st.sidebar.selectbox(
                "选择计划",
                list(plan_options.keys()),
                index=current_idx,
                label_visibility="collapsed",
            )
        
        new_plan_id = plan_options[selected_key]
        if new_plan_id != st.session_state.current_plan_id:
            st.session_state.current_plan_id = new_plan_id
            st.rerun()
        
        # 删除计划按钮 - 仅设置状态，不在侧边栏显示对话框
        with col2:
            if st.sidebar.button("🗑️", key="delete_plan_btn", help="删除该计划", use_container_width=True):
                st.session_state.delete_plan_confirm = True
    
    # 2. 计划进度（简洁显示）
    st.sidebar.divider()
    st.sidebar.markdown("### ⏱️ 计划进度")
    if current_plan:
        snap = service.get_schedule_snapshot(current_plan["id"])
        if snap:
            st.sidebar.markdown(f"**第 {snap['current_plan_day']} / {snap['max_plan_day']} 天**")
    else:
        st.sidebar.caption("暂无计划")
    
    # 2.5 今日规划
    st.sidebar.divider()
    st.sidebar.markdown("### 📍 今日规划")
    
    if current_plan:
        snap = service.get_schedule_snapshot(current_plan["id"])
        if snap and snap.get("today_tasks"):
            # 显示日期
            st.sidebar.markdown(f"**{str(date.today())}**")
            # 显示今日任务
            for task in snap["today_tasks"][:2]:  # 最多显示2个
                task_text = task.get('task', '')
                if len(task_text) > 50:
                    task_text = task_text[:50] + "..."
                st.sidebar.write(task_text)
        else:
            st.sidebar.markdown(f"**{str(date.today())}**")
            st.sidebar.caption("📭 今日无任务")
    else:
        st.sidebar.caption("📭 未选择计划")
    
    # 3. 菜单导航
    st.sidebar.divider()
    st.sidebar.markdown("### 📌 菜单")
    labels = [pair[0] for pair in NAV_ITEMS]
    
    # 检查是否有待处理的导航（如从打卡按钮来的）
    if hasattr(st.session_state, 'nav_page') and st.session_state.nav_page:
        page = st.session_state.nav_page
        st.session_state.nav_page = None  # 清除待处理导航
        # 更新radio的选择
        try:
            picked_idx = [pair[1] for pair in NAV_ITEMS].index(page)
            picked = labels[picked_idx]
        except ValueError:
            picked = labels[0]
    else:
        picked = st.sidebar.radio(
            "页面",
            labels,
            label_visibility="collapsed",
        )
        page = dict(NAV_ITEMS)[picked]
    
    # 4. 打卡功能
    st.sidebar.markdown("---")
    repo_checkin, is_checked = get_checkin_status(current_plan)
    if is_checked:
        st.sidebar.markdown("✅ **已打卡**")
        if st.sidebar.button("✕ 取消打卡", use_container_width=True, key="uncheckin_btn", help="取消今天的打卡记录"):
            if current_plan:
                repo_checkin.remove_daily_checkin(current_plan["id"], str(date.today()))
            st.rerun()
    else:
        if st.sidebar.button("📝 今日打卡 → 进度记录", use_container_width=True, key="checkin_btn", type="primary"):
            if current_plan:
                repo_checkin.add_daily_checkin(current_plan["id"], str(date.today()))
            st.session_state.nav_page = "学习计划与进度"
            st.rerun()

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

    # 阶段安排 - 不使用expander以避免DOM问题
    st.markdown("**🪜 阶段安排**")
    stages = plan_data.get("stages", [])
    if stages:
        for stage in stages:
            st.markdown(f"- **{stage.get('name', '阶段')}** · {stage.get('days', '待定')}")
    else:
        st.caption("暂无")

    # 里程碑 - 不使用expander
    st.markdown("**🎯 里程碑**")
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
    """学习进度反馈页面 - 每个任务独立选择"""
    st.markdown("# 📈 学习进度反馈")
    st.markdown("逐个确认今日每个任务的完成情况")
    
    if not current_plan:
        st.info("请先生成计划。")
        return

    snap = service.get_schedule_snapshot(current_plan["id"])
    if not snap:
        st.error("无法获取计划信息")
        return
    
    if snap:
        with st.expander("📌 计划信息", expanded=False):
            st.caption(
                f"{snap['today_iso']} · 起始 {snap['plan_start_date']} · "
                f"计划第 **{snap['current_plan_day']}** 天"
            )
        if snap["needs_attention"]:
            st.warning("有缺勤或某天完成率低于 50%，可改日期补录或去「学习计划与进度」中调整。")

    # 获取今日任务
    today_tasks = snap.get("today_tasks", [])
    
    if not today_tasks:
        st.info("今日无任务")
        return
    
    # 记录选择日期
    record_date = st.date_input(
        "📅 进度日期",
        value=date.today(),
        help="补录昨天请改选日期。",
    )
    
    st.divider()
    
    # 初始化session state来存储任务完成状态
    if "task_completions" not in st.session_state:
        st.session_state.task_completions = {}
    
    # 显示每个任务及其完成状态选项
    st.markdown("### ✅ 逐个确认完成情况")
    
    for task in today_tasks:
        task_id = task.get('day', 0)
        task_name = task.get('task', '')
        hours = task.get('estimated_hours', 0)
        
        st.markdown(f"**Day {task_id}：{task_name}** (~{hours}h)")
        
        # 解析子任务（用逗号分隔）
        sub_tasks = []
        for sep in ['，', ',']:
            if sep in task_name:
                sub_tasks = [t.strip() for t in task_name.split(sep) if t.strip()]
                break
        
        # 如果有多个子任务，为每个子任务显示完成状态选项
        if len(sub_tasks) > 1:
            st.caption(f"📝 该任务包含 {len(sub_tasks)} 个子任务，请逐一确认：")
            
            # 初始化子任务完成状态
            subtask_key = f"subtask_completions_{task_id}"
            if subtask_key not in st.session_state:
                st.session_state[subtask_key] = {}
            
            # 为每个子任务创建完成状态选项
            for idx, sub_task in enumerate(sub_tasks):
                st.caption(f"{idx + 1}. {sub_task}")
                
                sub_col1, sub_col2, sub_col3 = st.columns(3)
                current_sub_status = st.session_state[subtask_key].get(idx, None)
                
                with sub_col1:
                    if st.button(
                        "✅ 已完成",
                        key=f"sub_done_{task_id}_{idx}",
                        use_container_width=True,
                        type="primary" if current_sub_status == "✅" else "secondary"
                    ):
                        st.session_state[subtask_key][idx] = "✅"
                        st.rerun()
                
                with sub_col2:
                    if st.button(
                        "🟡 部分完成",
                        key=f"sub_partial_{task_id}_{idx}",
                        use_container_width=True,
                        type="primary" if current_sub_status == "🟡" else "secondary"
                    ):
                        st.session_state[subtask_key][idx] = "🟡"
                        st.rerun()
                
                with sub_col3:
                    if st.button(
                        "❌ 未完成",
                        key=f"sub_undone_{task_id}_{idx}",
                        use_container_width=True,
                        type="primary" if current_sub_status == "❌" else "secondary"
                    ):
                        st.session_state[subtask_key][idx] = "❌"
                        st.rerun()
                
                # 显示当前选择状态
                if current_sub_status:
                    st.caption(f"已选择：{current_sub_status}")
            
            st.divider()
        else:
            # 单任务模式 - 使用原有的三个选项
            col1, col2, col3 = st.columns(3)
            
            current_status = st.session_state.task_completions.get(task_id, None)
            
            with col1:
                if st.button(
                    "✅ 已完成",
                    key=f"btn_done_{task_id}",
                    use_container_width=True,
                    type="primary" if current_status == "✅ 已完成" else "secondary"
                ):
                    st.session_state.task_completions[task_id] = "✅ 已完成"
                    st.rerun()
            
            with col2:
                if st.button(
                    "🟡 部分完成",
                    key=f"btn_partial_{task_id}",
                    use_container_width=True,
                    type="primary" if current_status == "🟡 部分完成" else "secondary"
                ):
                    st.session_state.task_completions[task_id] = "🟡 部分完成"
                    st.rerun()
            
            with col3:
                if st.button(
                    "❌ 未完成",
                    key=f"btn_undone_{task_id}",
                    use_container_width=True,
                    type="primary" if current_status == "❌ 未完成" else "secondary"
                ):
                    st.session_state.task_completions[task_id] = "❌ 未完成"
                    st.rerun()
            
            # 显示当前选择状态
            if current_status:
                st.caption(f"已选择：{current_status}")
            else:
                st.caption("⏳ 请选择完成情况")
            
            st.divider()
    
    # 反馈信息
    st.markdown("### 📝 反馈信息")
    delay_reason = st.text_input("🤔 偏差原因（可选）", placeholder="时间不够 / 其他课挤占…", help="如果有未完成的任务，请说明原因")
    note = st.text_area("💭 备注（可选）", height=100, placeholder="随手记两句今天的收获或困难")

    if st.button("📤 提交进度并生成反馈", type="primary", use_container_width=True):
        # 检查是否所有任务都已选择
        all_selected = True
        for task in today_tasks:
            task_id = task.get('day', 0)
            task_name = task.get('task', '')
            
            # 检查是否有多个子任务
            sub_tasks = []
            for sep in ['，', ',']:
                if sep in task_name:
                    sub_tasks = [t.strip() for t in task_name.split(sep) if t.strip()]
                    break
            
            # 如果有多个子任务，检查所有子任务是否都已选择
            if len(sub_tasks) > 1:
                subtask_key = f"subtask_completions_{task_id}"
                selected_count = len(st.session_state.get(subtask_key, {}))
                if selected_count < len(sub_tasks):
                    st.error(f"❌ Day {task_id} 还有 {len(sub_tasks) - selected_count} 个子任务未选择")
                    all_selected = False
            else:
                # 单任务检查
                if task_id not in st.session_state.task_completions:
                    st.error(f"❌ 请完成 Day {task_id} 的选择")
                    all_selected = False
        
        if not all_selected:
            return
        
        # 计算完成度
        completed = sum(1 for status in st.session_state.task_completions.values() if "已完成" in status)
        partial = sum(1 for status in st.session_state.task_completions.values() if "部分完成" in status)
        total = len(st.session_state.task_completions)
        completion_ratio = ((completed + partial * 0.5) / total * 100) if total > 0 else 0
        
        # 构建进度数据
        progress_data = {
            "study_date": record_date.isoformat(),
            "completion_ratio": int(completion_ratio),
            "task_completions": st.session_state.task_completions,
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
    
    # 动态调整功能区域
    st.divider()
    st.markdown("### ⚡ 动态调整计划")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("根据今日进度重新调整后续任务安排")
    with col2:
        if st.button("🔄 生成调整建议", type="primary", use_container_width=True, key="adjust_plan_btn"):
            result = service.adjust_plan(current_plan["id"])
            if not result:
                st.warning("需要先至少一条进度记录（或满足日历缺勤时的合成条件）。")
            else:
                st.success("✨ 已更新计划，请刷新页面查看新的任务安排")



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
        st.markdown("## 📝 题目")
        for question in latest_generated_evaluation.get("questions", []):
            q_id = question.get('id', 'unknown')
            # 题号和类型
            st.markdown(f"### {q_id}. {question.get('type', '题')}")
            
            # 题目内容
            st.markdown(question.get('question', ''))
            
            # 考点
            st.markdown(f"**🎯 考点:** {question.get('check_point', '')}")
            
            # 参考答案 - 折叠展示
            with st.expander(f"💡 参考答案", expanded=False):
                st.markdown(question.get('reference_answer', '暂无参考答案'))
            
            st.divider()

        total_questions = len(latest_generated_evaluation.get("questions", []))
        score = st.number_input(
            "✅ 答对几题？",
            min_value=0,
            max_value=max(total_questions, 1),
            value=0,
            step=1,
        )
        
        # 答题简述 - 预设选项 + 自由输入
        st.markdown("#### ✏️ 答题简述（可选）")
        col1, col2 = st.columns(2)
        with col1:
            answer_preset = st.radio(
                "选择或自定义：",
                ["✨ 完全准确，思路清晰", "✓ 基本正确，有思路", "△ 思路不清，需要复习", "✗ 回答有误", "🗣️ 自定义输入"],
                key="answer_preset",
                label_visibility="collapsed"
            )
        with col2:
            if answer_preset == "🗣️ 自定义输入":
                user_answers = st.text_area("输入你的答题思路", placeholder="一两句即可", key="answer_custom", height=100)
            else:
                user_answers = answer_preset
                st.text_area("已选择", value=user_answers, disabled=True, key="answer_display", height=100)
        
        st.divider()
        
        # 自我总结 - 预设选项 + 自由输入
        st.markdown("#### 🪞 自我总结（可选）")
        col3, col4 = st.columns(2)
        with col3:
            summary_preset = st.radio(
                "选择或自定义：",
                ["✨ 完全掌握，继续加油", "✓ 基本理解，多做练习", "△ 某个部分不太懂", "✗ 需要重新学习", "🗣️ 自定义输入"],
                key="summary_preset",
                label_visibility="collapsed"
            )
        with col4:
            if summary_preset == "🗣️ 自定义输入":
                evaluation_summary = st.text_area("输入你的总结", placeholder="哪里卡住了", key="summary_custom", height=100)
            else:
                evaluation_summary = summary_preset
                st.text_area("已选择", value=evaluation_summary, disabled=True, key="summary_display", height=100)

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


def render_plan_and_progress_combined(service, current_plan):
    """合并的学习计划与进度页面 - 使用标签页"""
    st.markdown("# 📋 学习计划与进度")
    
    if not current_plan:
        st.info("📭 暂无计划，请先生成一个。")
        return
    
    snap = service.get_schedule_snapshot(current_plan["id"])
    
    # 创建两个标签页
    tab1, tab2 = st.tabs(["📋 计划详情", "📊 进度与反馈"])
    
    # 标签页1：计划详情
    with tab1:
        st.markdown("### 📋 计划详情")
        render_plan(current_plan, snap)
    
    # 标签页2：进度与反馈（包含动态调整按钮）
    with tab2:
        render_progress(service, current_plan)


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

# 获取当前计划（通过render_sidebar中的逻辑）
current_plan = None
if st.session_state.current_plan_id:
    repo = StudyRepository()
    current_plan = repo.get_plan_by_id(st.session_state.current_plan_id)

# 侧边栏：菜单、今日规划、日期等
page = render_sidebar(service, current_plan)

# 侧边栏：登出
show_logout_button()

# ========== 删除计划确认对话框 - 在页面顶部显示 ==========
if st.session_state.get("delete_plan_confirm") and current_plan:
    st.warning("⚠️ 确定要删除该学习计划吗？删除后无法恢复。")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("❌ 取消删除", use_container_width=True, key="cancel_delete"):
            st.session_state.delete_plan_confirm = False
            st.rerun()
    with col2:
        if st.button("🗑️ 确认删除", use_container_width=True, key="confirm_delete", type="secondary"):
            repo = StudyRepository()
            repo.update_plan_status(current_plan["id"], "deleted")
            st.session_state.current_plan_id = None
            st.session_state.delete_plan_confirm = False
            st.success("✓ 已删除计划")
            st.balloons()
            import time
            time.sleep(1)
            st.rerun()
    st.divider()

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

elif page == "学习计划与进度":
    render_plan_and_progress_combined(service, current_plan)

elif page == "学习检测":
    render_evaluation(service, current_plan)

