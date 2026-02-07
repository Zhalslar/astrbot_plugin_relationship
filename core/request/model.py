from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import ClassVar, Dict, Optional

# ==========================================================
# BaseRequest
# ==========================================================


class BaseRequest(ABC):
    """
    申请基类
    - 统一 display / parse / raw 构造
    - 调用方不需要区分好友 / 群
    """

    _HEADER: ClassVar[str]
    _FIELD_MAP: ClassVar[Dict[str, str]]

    # -------------------------
    # 展示
    # -------------------------
    def to_display_text(self) -> str:
        lines = [self._HEADER]
        for cn, field in self._FIELD_MAP.items():
            lines.append(f"{cn}：{getattr(self, field)}")
        return "\n".join(lines)

    # -------------------------
    # 从展示文本反序列化
    # -------------------------
    @classmethod
    def from_display_text(cls, text: str) -> Optional["BaseRequest"]:
        for sub in cls.__subclasses__():
            req = sub._from_display_text(text)
            if req:
                return req
        return None

    @classmethod
    def _from_display_text(cls, text: str) -> Optional["BaseRequest"]:
        if cls._HEADER not in text:
            return None

        kwargs = {}
        for line in text.splitlines():
            if "：" not in line:
                continue
            key, _, val = line.partition("：")
            field = cls._FIELD_MAP.get(key.strip())
            if field:
                kwargs[field] = val.strip()

        required = set(cls._FIELD_MAP.values()) - {"comment"}
        if not required <= kwargs.keys():
            return None

        kwargs.setdefault("comment", "无")
        return cls(**kwargs)  # type: ignore

    # -------------------------
    # 从 raw_message 构造
    # -------------------------
    @classmethod
    async def from_raw(cls, client, raw) -> Optional["BaseRequest"]:
        if not isinstance(raw, dict):
            return None

        for sub in cls.__subclasses__():
            req = await sub._from_raw(client, raw)
            if req:
                return req
        return None

    @classmethod
    @abstractmethod
    async def _from_raw(cls, client, raw: dict) -> Optional["BaseRequest"]:
        raise NotImplementedError

    # -------------------------
    # 统一访问接口
    # -------------------------
    @property
    @abstractmethod
    def requester_id(self) -> str:
        """发起申请的人 ID"""
        raise NotImplementedError


# ==========================================================
# FriendRequest
# ==========================================================


@dataclass
class FriendRequest(BaseRequest):
    nickname: str
    user_id: str
    flag: str
    comment: str

    _HEADER = "【好友申请】同意/拒绝："
    _FIELD_MAP = {
        "昵称": "nickname",
        "QQ号": "user_id",
        "flag": "flag",
        "验证信息": "comment",
    }

    @property
    def requester_id(self) -> str:
        return self.user_id

    @classmethod
    async def _from_raw(cls, client, raw: dict) -> Optional["FriendRequest"]:
        if not (
            raw.get("post_type") == "request" and raw.get("request_type") == "friend"
        ):
            return None

        user_id = raw.get("user_id", 0)
        info = await client.get_stranger_info(user_id=int(user_id)) or {}

        return cls(
            nickname=info.get("nickname") or "未知昵称",
            user_id=str(user_id),
            flag=raw.get("flag", ""),
            comment=raw.get("comment") or "无",
        )


# ==========================================================
# GroupRequest
# ==========================================================


@dataclass
class GroupRequest(BaseRequest):
    inviter_nickname: str
    inviter_id: str
    group_name: str
    group_id: str
    flag: str
    comment: str

    _HEADER = "【群邀请】同意/拒绝："
    _FIELD_MAP = {
        "邀请人昵称": "inviter_nickname",
        "邀请人QQ": "inviter_id",
        "群名称": "group_name",
        "群号": "group_id",
        "flag": "flag",
        "验证信息": "comment",
    }

    @property
    def requester_id(self) -> str:
        return self.inviter_id

    @classmethod
    async def _from_raw(cls, client, raw: dict) -> Optional["GroupRequest"]:
        if not (
            raw.get("post_type") == "request"
            and raw.get("request_type") == "group"
            and raw.get("sub_type") == "invite"
        ):
            return None

        inviter_id = raw.get("user_id", 0)
        group_id = raw.get("group_id", 0)

        inviter_info = await client.get_stranger_info(user_id=int(inviter_id)) or {}
        group_info = await client.get_group_info(group_id=group_id)

        return cls(
            inviter_nickname=inviter_info.get("nickname") or "未知昵称",
            inviter_id=str(inviter_id),
            group_name=group_info.get("group_name") or "未知群名",
            group_id=str(group_id),
            flag=raw.get("flag", ""),
            comment=raw.get("comment") or "无",
        )
