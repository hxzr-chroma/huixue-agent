"""
用户认证模块
处理登录、注册、密码验证等
"""

import hashlib
import json
from storage.db import get_connection


def hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(username: str, password: str) -> dict:
    """
    注册新用户
    返回: {"success": bool, "message": str, "user_id": int}
    """
    if not username or not password:
        return {"success": False, "message": "用户名和密码不能为空"}

    if len(username) < 3:
        return {"success": False, "message": "用户名至少3个字符"}

    if len(password) < 6:
        return {"success": False, "message": "密码至少6个字符"}

    password_hash = hash_password(password)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
                """,
                (username, password_hash),
            )
            user_id = cursor.lastrowid
            return {"success": True, "message": "注册成功", "user_id": user_id}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return {"success": False, "message": "用户名已存在"}
        return {"success": False, "message": f"注册失败: {str(e)}"}


def login_user(username: str, password: str) -> dict:
    """
    用户登录
    返回: {"success": bool, "message": str, "user_id": int, "username": str}
    """
    if not username or not password:
        return {"success": False, "message": "用户名和密码不能为空"}

    password_hash = hash_password(password)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, username FROM users
                WHERE username = ? AND password_hash = ?
                """,
                (username, password_hash),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "success": True,
                    "message": "登录成功",
                    "user_id": row["id"],
                    "username": row["username"],
                }
            else:
                return {"success": False, "message": "用户名或密码错误"}
    except Exception as e:
        return {"success": False, "message": f"登录失败: {str(e)}"}


def get_user_by_id(user_id: int) -> dict:
    """获取用户信息"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            return {"id": row["id"], "username": row["username"]}
        return None
