"""
Streamlit 登录/注册页面
"""

import streamlit as st
from utils.auth import register_user, login_user


def show_auth_page():
    """显示登录/注册页面"""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("---")
        st.markdown("# 📘 AI 学习助手")
        st.markdown("### 智能学习规划系统")
        st.markdown("---")

        # 选择登录或注册
        auth_mode = st.radio(
            "选择操作",
            ["📝 登录", "🆕 注册"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if auth_mode == "📝 登录":
            st.subheader("🔑 登录账户", divider="blue")

            with st.form("login_form", clear_on_submit=False):
                username = st.text_input(
                    "用户名",
                    placeholder="输入你的用户名",
                    key="login_username",
                )
                password = st.text_input(
                    "密码",
                    type="password",
                    placeholder="输入你的密码",
                    key="login_password",
                )
                submitted = st.form_submit_button("🚀 登录", use_container_width=True)

                if submitted:
                    if not username or not password:
                        st.error("❌ 用户名和密码不能为空")
                    else:
                        result = login_user(username, password)
                        if result["success"]:
                            st.success(result["message"])
                            st.session_state.user_id = result["user_id"]
                            st.session_state.username = result["username"]
                            st.session_state.logged_in = True
                            st.rerun()
                        else:
                            st.error(result["message"])

        else:  # 注册
            st.subheader("✨ 创建新账户", divider="green")

            with st.form("register_form", clear_on_submit=True):
                username = st.text_input(
                    "用户名",
                    placeholder="3-20个字符（仅字母、数字、下划线）",
                    key="reg_username",
                )
                password = st.text_input(
                    "密码",
                    type="password",
                    placeholder="至少6个字符",
                    key="reg_password",
                )
                password_confirm = st.text_input(
                    "确认密码",
                    type="password",
                    placeholder="再次输入密码",
                    key="reg_password_confirm",
                )
                submitted = st.form_submit_button("✨ 注册", use_container_width=True)

                if submitted:
                    if password != password_confirm:
                        st.error("❌ 两次输入的密码不一致")
                    else:
                        result = register_user(username, password)
                        if result["success"]:
                            st.success(result["message"])
                            st.info("✅ 注册成功！现在你可以登录了")
                        else:
                            st.error(result["message"])

        st.markdown("---")
        st.markdown(
            """
            <div style='text-align: center; color: gray; font-size: 12px;'>
                💡 提示：此页面由 Streamlit + DeepSeek AI 提供支持
            </div>
            """,
            unsafe_allow_html=True,
        )
