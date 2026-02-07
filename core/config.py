from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context


class ConfigNode:
    """
    配置节点, 把 dict 变成强类型对象。

    规则：
    - schema 来自子类类型注解
    - 声明字段：读写，写回底层 dict
    - 未声明字段和下划线字段：仅挂载属性，不写回
    - 支持 ConfigNode 多层嵌套（lazy + cache）
    """

    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}
    _FIELDS_CACHE: dict[type, set[str]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    @classmethod
    def _fields(cls) -> set[str]:
        return cls._FIELDS_CACHE.setdefault(
            cls,
            {k for k in cls._schema() if not k.startswith("_")},
        )

    @staticmethod
    def _is_optional(tp: type) -> bool:
        if get_origin(tp) in (Union, UnionType):
            return type(None) in get_args(tp)
        return False

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key, tp in self._schema().items():
            if key.startswith("_"):
                continue
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            if self._is_optional(tp):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] 缺少字段: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._fields():
            value = self._data.get(key)
            tp = self._schema().get(key)

            if isinstance(tp, type) and issubclass(tp, ConfigNode):
                children: dict[str, ConfigNode] = self.__dict__["_children"]
                if key not in children:
                    if not isinstance(value, MutableMapping):
                        raise TypeError(
                            f"[config:{self.__class__.__name__}] "
                            f"字段 {key} 期望 dict，实际是 {type(value).__name__}"
                        )
                    children[key] = tp(value)
                return children[key]

            return value

        if key in self.__dict__:
            return self.__dict__[key]

        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._fields():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)

    def raw_data(self) -> Mapping[str, Any]:
        """
        底层配置 dict 的只读视图
        """
        return MappingProxyType(self._data)

    def save_config(self) -> None:
        """
        保存配置到磁盘（仅允许在根节点调用）
        """
        if not isinstance(self._data, AstrBotConfig):
            raise RuntimeError(
                f"{self.__class__.__name__}.save_config() 只能在根配置节点上调用"
            )
        self._data.save_config()


# ====================== 插件自定义配置 ======================

class CheckConfig(ConfigNode):
    count: int
    batch_size: int
    check_new_group: bool
    delay: int

class RequestConfig(ConfigNode):
    # 黑名单
    group_blacklist: list[str]
    user_blacklist: list[str]

    # 群邀请
    auto_agree_group: bool
    auto_reject_group: bool

    # 好友请求
    auto_agree_friend: bool
    auto_reject_friend: bool


class NoticeConfig(ConfigNode):
    block_small_group: bool
    min_group_size: int
    max_group_size: int
    max_group_capacity: int
    max_ban_days: int
    kick_block_user: bool
    kick_block_group: bool
    mutual_blacklist: list[str]

    def __init__(self, data: MutableMapping[str, Any]):
        super().__init__(data)
        self.max_duration = self.max_ban_days * 24 * 60 * 60
    def is_mutual(self, group_id: str) -> bool:
        return group_id in self.mutual_blacklist

class ExpansionConfig:
    group_answer: str
    friend_verify: str

class PluginConfig(ConfigNode):
    manage_group: str
    manage_users: list[str]
    check: CheckConfig
    request: RequestConfig
    notice: NoticeConfig
    expansion: ExpansionConfig

    def __init__(self, config: AstrBotConfig, context: Context):
        super().__init__(config)

        # 1. 管理员 ID
        self.admins_id = self._clean_ids(context.get_config().get("admins_id", []))
        self.admin_id = self.admins_id[0] if self.admins_id else None

        # 2. 审批员
        self.manage_users = self._clean_ids(self.manage_users)
        self._append_admin_to_manage_users()

        # 3. 审批群号校验
        self.manage_group = (
            self.manage_group if str(self.manage_group).isdigit() else ""
        )

        # 4. 合法性提醒
        if not self.manage_group and not self.manage_users:
            logger.warning("未配置审批群或审批员，将无法发送审批消息")

        # 5. 黑名单引用
        self.group_blacklist = self.request.group_blacklist
        self.user_blacklist = self.request.user_blacklist

        self.save_config()


    @staticmethod
    def _clean_ids(ids: list) -> list[str]:
        """过滤并规范化数字 ID"""
        return [str(i) for i in ids if str(i).isdigit()]

    def _append_admin_to_manage_users(self) -> None:
        """确保管理员在审批员列表中"""
        if self.admin_id and self.admin_id not in self.manage_users:
            self.manage_users.append(self.admin_id)

    def is_black_group(self, group_id: str) -> bool:
        return group_id in self.group_blacklist

    def add_black_group(self, group_id: str | int) -> None:
        """将群聊加入黑名单"""
        gid = str(group_id)
        if gid not in self.group_blacklist:
            self.group_blacklist.append(gid)
            self.save_config()
            logger.info(f"群聊 {gid} 已加入黑名单")

    def remove_black_group(self, group_id: str | int) -> None:
        """将群聊从黑名单移除"""
        gid = str(group_id)
        if gid in self.group_blacklist:
            self.group_blacklist.remove(gid)
            self.save_config()
            logger.info(f"群聊 {gid} 已从黑名单移除")

    def is_block_user(self, user_id: str) -> bool:
        """判断用户是否被拉黑"""
        return user_id in self.user_blacklist
    
    def add_block_user(self, user_id: str | int) -> None:
        """将用户加入拉黑名单"""
        uid = str(user_id)
        if uid not in self.user_blacklist:
            self.user_blacklist.append(uid)
            self.save_config()
            logger.info(f"用户 {uid} 已加入拉黑名单")

    def remove_block_user(self, user_id: str | int) -> None:
        """将用户从拉黑名单移除"""
        uid = str(user_id)
        if uid in self.user_blacklist:
            self.user_blacklist.remove(uid)
            self.save_config()
            logger.info(f"用户 {uid} 已从拉黑名单移除")

    def is_manage_user(self, user_id: str) -> bool:
        """判断用户是否为审批员"""
        return user_id in self.manage_users

    def add_manage_user(self, user_id: str | int) -> None:
        """将用户加入审批员"""
        uid = str(user_id)
        if uid not in self.manage_users:
            self.manage_users.append(uid)
            self.save_config()
            logger.info(f"用户 {uid} 已加入审批员")

    def remove_manage_user(self, user_id: str | int) -> None:
        """将用户从审批员移除"""
        uid = str(user_id)
        if uid in self.manage_users:
            self.manage_users.remove(uid)
            self.save_config()
            logger.info(f"用户 {uid} 已从审批员移除")

