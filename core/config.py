# config.py
from __future__ import annotations

import json
from typing import Any

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context


class PluginConfig:
    """
    强校验、无默认值、属性访问、可安全保存
    """

    # --------------- 必填字段声明 ---------------
    manage_group: str
    admin_id: str
    manage_users: list[str]
    max_ban_days: int
    block_small_group: bool
    min_group_size: int
    max_group_size: int
    max_group_capacity: int
    group_blacklist: list[str]
    mutual_blacklist: list[str]
    auto_check_messages: bool
    check_delay: int
    msg_check_count: int
    batch_size: int
    # ------------------------------------------

    def __init__(self, context: Context, astr_config: AstrBotConfig):
        # 基础字段（绕过 __setattr__）
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "astr_config", astr_config)

        # 原始配置（唯一真源）
        raw = dict(astr_config)
        object.__setattr__(self, "_raw", raw)

        # 强校验
        for key in self.__annotations__:
            if key not in raw:
                raise KeyError(f"缺少必填配置键: {key}")

        # 归一化
        self._normalize()

        # 首次保存（写回规范化结果）
        self.save()

    # ---------- 属性代理 ----------
    def __getattr__(self, key: str) -> Any:
        if key in self._raw:
            return self._raw[key]
        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self.__annotations__:
            self._raw[key] = value
        else:
            object.__setattr__(self, key, value)

    # ---------- 内部受控写 ----------
    def _set(self, key: str, value: Any) -> None:
        self._raw[key] = value

    # ---------- 内部归一化 ----------
    def _normalize(self) -> None:
        # 1. 管理员 ID（来自全局配置）
        admins_id: list[str] = self.context.get_config().get("admins_id", [])
        valid_admins = [str(i) for i in admins_id if str(i).isdigit()]
        admin_id = valid_admins[0] if valid_admins else ""

        self._set("admin_id", admin_id)

        # 2. 审批员列表（读属性，写回 raw）
        users = {str(u) for u in self.manage_users if str(u).isdigit()}
        if admin_id:
            users.add(admin_id)

        self._set("manage_users", list(users))

        # 3. 审批群号校验
        if not str(self.manage_group).isdigit():
            self._set("manage_group", "")

        # 4. 合法性提醒
        if not self.manage_group and not self.manage_users:
            logger.warning("未配置审批群或审批员，将无法发送审批消息")

    # ---------- 保存 ----------
    def save(self) -> None:
        """将当前配置写回 AstrBotConfig"""
        self.astr_config.save_config(self._raw)

    # ---------- 工具 ----------
    def to_dict(self) -> dict[str, Any]:
        """返回安全的深拷贝"""
        return json.loads(json.dumps(self._raw))
