# 用户登录注册和多任务管理功能实现

## 功能概述

已成功为 AI 学习助手应用添加以下功能：

### 1. 用户登录/注册系统 ✅
- **独立的登录页面**：用户未登录时，显示专门的登录/注册界面，不与主应用混在一起
- **安全的密码存储**：使用 SHA256 哈希加密存储密码
- **用户验证**：登录时验证用户名和密码
- **注册表单**：新用户可注册创建账户

### 2. 多任务/多计划管理 ✅
- **一用户多计划**：每个用户可创建和管理多个学习计划
- **计划列表**：侧边栏显示当前用户所有计划
- **计划切换**：网页中可快速切换不同的计划
- **计划名称**：支持为每个计划自定义名称

### 3. 前端布局改进 ✅
- **布局不改变**：保持原有的侧边栏 + 主内容区布局
- **登录信息显示**：侧边栏底部显示当前登录用户
- **退出按钮**：方便用户登出

---

## 技术实现

### 数据库变更

#### Users 表（新增密码字段）
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,          -- 新增
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

#### Study Plans 表（新增计划名称和用户隔离）
```sql
CREATE TABLE IF NOT EXISTS study_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,             -- 关联用户
    plan_name TEXT DEFAULT '学习计划',    -- 新增：计划名称
    raw_input TEXT NOT NULL,
    parsed_goal_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    plan_text TEXT NOT NULL,
    plan_start_date TEXT,                 -- 计划开始日期
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### 新增模块

#### 1. `utils/auth.py` - 认证核心逻辑
```python
- hash_password()      # 密码哈希
- register_user()      # 用户注册
- login_user()         # 用户登录
- get_user_by_id()     # 获取用户信息
```

#### 2. `utils/auth_ui.py` - 登录/注册UI
- 独立的登录注册页面，使用 Streamlit 元素
- 可在"登录"和"注册"标签之间切换
- 完整的表单验证和错误提示

### 修改的文件

#### `streamlit_app.py` - 主应用
新增功能：
- `initialize_app()` - 初始化应用状态
- `check_login()` - 检查用户登录状态
- `show_plan_selector()` - 侧边栏计划选择器
- `show_logout_button()` - 登出按钮

主流程变更：
1. 应用启动前检查登录状态
2. 未登录 → 显示登录页面
3. 已登录 → 显示主应用
4. 用户ID存储在 `st.session_state`中
5. 每个用户只能看到自己的计划

#### `storage/repository.py` - 数据库操作
新增方法：
- `get_user_plans(user_id)` - 获取用户所有计划
- `update_plan_name(plan_id, plan_name)` - 更新计划名称
- 修改 `_row_to_plan_dict()` 包含 plan_name

#### `storage/db.py` - 数据库初始化
- 添加 password_hash 字段到 users 表
- 添加 plan_name 字段到 study_plans 表
- 添加 plan_start_date 字段到 study_plans 表

### Session State 管理

```python
st.session_state.logged_in      # 登录状态 (bool)
st.session_state.user_id        # 当前用户ID (int)
st.session_state.username       # 用户名 (str)
st.session_state.current_plan_id # 当前查看的计划ID (int)
```

---

## 使用流程

### 第一次使用

1. **启动应用** → 看到登录/注册界面
2. **点击"🆕 注册"标签** 
3. **填写用户名和密码**（用户名≥3字符，密码≥6字符）
4. **点击"✨ 注册"按钮**
5. **返回"📝 登录"标签，登录账户**
6. **进入主应用**

### 日常使用

1. **登录后**进入首页
2. **点击"✨ 学习计划生成"**创建新计划
3. **给计划命名**（可选）
4. **输入学习目标**并生成计划
5. **在侧边栏"📚 我的学习计划"中**选择要查看的计划
6. **完成后点击侧边栏底部的"退出"登出**

---

## 安全特性

✅ **密码加密**：使用 SHA256 哈希存储，不存储明文密码
✅ **用户隔离**：每个用户只能看到自己的计划
✅ **会话管理**：通过 session_state 管理登录状态
✅ **数据关联**：通过 user_id 关联用户和计划

---

## 文件结构

```
streamlit_app.py               ← 主应用（已更新）
├── utils/
│   ├── auth.py              ← 新增：认证逻辑
│   ├── auth_ui.py           ← 新增：登录UI
│   └── ...
├── storage/
│   ├── db.py                ← 已修改：新增表字段
│   └── repository.py        ← 已修改：新增方法
└── ...
```

---

## 部署说明

### 本地运行
```bash
streamlit run streamlit_app.py
```

### Streamlit Cloud 部署
无需更改，直接推送到 GitHub 即可自动部署。

### 数据库迁移
- **本地开发**：数据库会自动创建新表和字段
- **无旧数据丢失**：使用 `CREATE TABLE IF NOT EXISTS`

---

## 后续功能规划

- [ ] 社交登登出（Google OAuth）
- [ ] 忘记密码重置
- [ ] 用户个人资料编辑
- [ ] 计划分享功能
- [ ] 计划导出（PDF）
- [ ] 团队合作功能

---

## 已实现的需求

✅ 用户登录注册  
✅ 多任务分类（一个用户多个计划）  
✅ 不改变前端现有布局  
✅ 登录注册不挤在一起（独立页面）  
✅ 继续使用 Streamlit 部署  

