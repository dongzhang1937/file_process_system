"""
用户配置选中服务
每个用户每种配置类型（llm/embedding/search/sql_db）只能选中一个，互不影响。
底层使用 user_selected_configs 表，UPSERT 语义。
"""
from __future__ import annotations
from typing import Any
from config.db_config import fetch_one, dml_sql


def select_config(username: str, config_type: str, config_id: int) -> bool:
    """
    选中配置（互斥）：同一用户同一类型只能选一个
    使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 UPSERT
    """
    sql = """
        INSERT INTO user_selected_configs (username, config_type, config_id, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE config_id = VALUES(config_id), updated_at = NOW()
    """
    dml_sql(sql, (username, config_type, config_id))
    return True


def get_selected_config_id(username: str, config_type: str) -> int | None:
    """
    获取用户选中的配置 ID
    返回 None 表示用户未主动选择（应 fallback 到 admin 的默认配置）
    """
    sql = "SELECT config_id FROM user_selected_configs WHERE username = %s AND config_type = %s"
    row = fetch_one(sql, (username, config_type))
    return row['config_id'] if row else None


def clear_selection(username: str, config_type: str) -> bool:
    """清除用户对某类配置的选中"""
    sql = "DELETE FROM user_selected_configs WHERE username = %s AND config_type = %s"
    affected = dml_sql(sql, (username, config_type))
    return affected > 0


def get_effective_config_id(username: str, config_type: str, admin_username: str = 'asd') -> int | None:
    """
    获取用户实际生效的配置 ID（优先自己的选择，fallback 到 admin 的选择）
    """
    # 先查用户自己的选择
    selected = get_selected_config_id(username, config_type)
    if selected is not None:
        return selected
    # fallback: 查 admin 的选择
    if username != admin_username:
        return get_selected_config_id(admin_username, config_type)
    return None
