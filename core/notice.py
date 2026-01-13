import asyncio
from dataclasses import dataclass

from aiocqhttp import CQHttp

from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .forward import ForwardHandle
from .utils import convert_duration_advanced, get_nickname


# =========================
# Notice 消息模型（只读事实）
# =========================
@dataclass(frozen=True)
class NoticeMessage:
    post_type: str
    notice_type: str
    sub_type: str

    user_id: str
    self_id: str
    group_id: str
    operator_id: str

    duration: int = 0

    @classmethod
    def from_raw(cls, raw: dict) -> "NoticeMessage":
        return cls(
            post_type=raw.get("post_type", ""),
            notice_type=raw.get("notice_type", ""),
            sub_type=raw.get("sub_type", ""),
            user_id=str(raw.get("user_id", "")),
            self_id=str(raw.get("self_id", "")),
            group_id=str(raw.get("group_id", "")),
            operator_id=str(raw.get("operator_id", "")),
            duration=int(raw.get("duration", 0)),
        )


# =========================
# 业务结果对象（强语义）
# =========================
@dataclass
class NoticeResult:
    admin_reply: str = ""
    operator_reply: str = ""

    delay_check: bool = False
    leave_group: bool = False

    add_group_blacklist: bool = False


# =========================
# 业务决策服务（无副作用）
# =========================
class NoticeDecisionService:
    """仅负责：业务判断 + 生成结果"""

    REPLY_TEMPLATES = {
        "admin_set": {
            "admin": "哇！我成为了 {group_name}({group_id}) 的管理员",
            "operator": "芜湖~拿到管理了",
        },
        "admin_unset": {
            "admin": "呜呜ww.. 我在 {group_name}({group_id}) 的管理员被撤了",
            "operator": "呜呜ww..干嘛撤掉我管理",
        },
        "ban_lift": {
            "admin": "好耶！{operator_name} 在 {group_name}({group_id}) 解除了我的禁言",
            "operator": "感谢解禁",
        },
        "ban_set": {
            "admin": "呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{duration_str}",
        },
        "ban_exceed": {
            "suffix": "\n禁言时间超过{max_duration_str}，我退群了",
        },
        "kicked": {
            "admin": "呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单",
        },
        "invited": {
            "admin": "主人..我被 {operator_name} 拉进了 {group_name}({group_id})。",
        },
        "invited_blacklist": {
            "suffix": "\n群聊 {group_name}({group_id}) 在黑名单里，我退群了",
            "operator": "把我踢了还想要我回来？退了退了",
        },
        "invited_capacity_exceeded": {
            "suffix": "\n我已经加了{group_count}个群（超过了{max_capacity}个），这群我退了",
            "operator": "我最多只能加{max_capacity}个群，现在已经加了{group_count}个群，请不要拉我进群了",
        },
        "invited_mutual_blacklist": {
            "suffix": "\n检测到群内存在互斥成员 {member_name}({member_id})，这群我退了",
            "operator": "我不想和{member_name}({member_id})在同一个群里，退了",
        },
        "invited_small_group": {
            "suffix": "\n群人数 {member_count} ≤ {min_size}，小群我退了",
            "operator": "小群不加，人数 {member_count} ≤ {min_size}",
        },
        "invited_large_group": {
            "suffix": "\n群人数 {member_count} > {max_size}，大群我退了",
            "operator": "大群不加，人数 {member_count} > {max_size}",
        },
    }

    def __init__(
        self,
        client: CQHttp,
        message: NoticeMessage,
        config: PluginConfig,
    ):
        self.cfg = config
        self.client = client
        self.msg = message
        self.max_duration = self.cfg.max_ban_days * 24 * 60 * 60

        self._group_name: str | None = None
        self._operator_name: str | None = None

    # ---------
    # 公共入口
    # ---------
    async def decide(self) -> NoticeResult:
        result = NoticeResult()

        match (self.msg.notice_type, self.msg.sub_type):
            case ("group_admin", _):
                await self._handle_admin_change(result)
            case ("group_ban", _):
                await self._handle_ban(result)
            case ("group_decrease", "kick_me"):
                await self._handle_kicked(result)
            case ("group_increase", "invite"):
                await self._handle_invited(result)

        return result

    # ----------------
    # 基础信息获取
    # ----------------
    async def _get_group_name(self) -> str:
        if self._group_name is None:
            info = await self.client.get_group_info(group_id=int(self.msg.group_id))
            self._group_name = info.get("group_name", "")
        return self._group_name

    async def _get_operator_name(self) -> str:
        if self._operator_name is None:
            self._operator_name = await get_nickname(
                self.client,
                user_id=int(self.msg.operator_id),
                group_id=self.msg.group_id,
            )
        return self._operator_name

    def _reply(self, key: str, role: str = "admin", **kwargs) -> str:
        tpl = self.REPLY_TEMPLATES.get(key, {}).get(role, "")
        return tpl.format(**kwargs) if tpl else ""

    def _suffix(self, key: str, **kwargs) -> str:
        tpl = self.REPLY_TEMPLATES.get(key, {}).get("suffix", "")
        return tpl.format(**kwargs) if tpl else ""

    # ----------------
    # 各事件处理
    # ----------------
    async def _handle_admin_change(self, result: NoticeResult):
        group_name = await self._get_group_name()
        ctx = {"group_name": group_name, "group_id": self.msg.group_id}

        if self.msg.sub_type == "set":
            result.admin_reply = self._reply("admin_set", **ctx)
            result.operator_reply = self._reply("admin_set", "operator")
        else:
            result.admin_reply = self._reply("admin_unset", **ctx)
            result.operator_reply = self._reply("admin_unset", "operator")

    async def _handle_ban(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        ctx = {
            "group_name": group_name,
            "group_id": self.msg.group_id,
            "operator_name": operator_name,
        }

        if self.msg.duration == 0:
            result.admin_reply = self._reply("ban_lift", **ctx)
            result.operator_reply = self._reply("ban_lift", "operator")
            return

        duration_str = convert_duration_advanced(self.msg.duration)
        result.admin_reply = self._reply("ban_set", duration_str=duration_str, **ctx)

        if self.msg.duration > self.max_duration:
            max_str = convert_duration_advanced(self.max_duration)
            result.admin_reply += self._suffix("ban_exceed", max_duration_str=max_str)
            result.leave_group = True

    async def _handle_kicked(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        result.admin_reply = self._reply(
            "kicked",
            operator_name=operator_name,
            group_name=group_name,
            group_id=self.msg.group_id,
        )
        result.leave_group = True
        result.add_group_blacklist = True

    async def _handle_invited(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        ctx = {
            "group_name": group_name,
            "group_id": self.msg.group_id,
            "operator_name": operator_name,
        }

        result.admin_reply = self._reply("invited", **ctx)

        # 审批员拉群直接放行，其余人按规则过滤
        if self.msg.operator_id not in self.cfg.manage_users:
            if await self._check_blacklist(result, ctx):
                return
            if await self._check_group_size(result, ctx):
                return
            if await self._check_capacity(result, ctx):
                return
            if await self._check_mutual_blacklist(result, ctx):
                return
        # 走到这里说明要么审批员拉群，要么全部检查通过
        result.delay_check = True

    # ----------------
    # 各种检查
    # ----------------
    async def _check_blacklist(self, result: NoticeResult, ctx: dict) -> bool:
        if self.msg.group_id in self.cfg.group_blacklist:
            result.admin_reply += self._suffix("invited_blacklist", **ctx)
            result.operator_reply = self._reply("invited_blacklist", "operator")
            result.leave_group = True
            return True
        return False

    async def _check_capacity(self, result: NoticeResult, ctx: dict) -> bool:
        group_list = await self.client.get_group_list()
        max_cap = self.cfg.max_group_capacity

        if len(group_list) > max_cap:
            result.admin_reply += self._suffix(
                "invited_capacity_exceeded",
                group_count=len(group_list),
                max_capacity=max_cap,
                **ctx,
            )
            result.operator_reply = self._reply(
                "invited_capacity_exceeded",
                "operator",
                group_count=len(group_list),
                max_capacity=max_cap,
            )
            result.leave_group = True
            return True
        return False

    async def _check_mutual_blacklist(self, result: NoticeResult, ctx: dict) -> bool:
        mutual = set(self.cfg.mutual_blacklist)
        mutual.discard(self.msg.user_id)

        members = await self.client.get_group_member_list(
            group_id=int(self.msg.group_id)
        )
        member_ids = {str(m["user_id"]) for m in members}

        common = member_ids & mutual
        if not common:
            return False

        member_id = common.pop()
        member_name = await get_nickname(
            self.client,
            user_id=int(member_id),
            group_id=self.msg.group_id,
        )

        result.admin_reply += self._suffix(
            "invited_mutual_blacklist",
            member_name=member_name,
            member_id=member_id,
            **ctx,
        )
        result.operator_reply = self._reply(
            "invited_mutual_blacklist",
            "operator",
            member_name=member_name,
            member_id=member_id,
        )
        result.leave_group = True
        return True

    async def _check_group_size(self, result: NoticeResult, ctx: dict) -> bool:
        """
        返回 True 表示已触发退群，不再继续后续检查
        """
        # 取当前群人数
        group_info = await self.client.get_group_info(
            group_id=int(self.msg.group_id), no_cache=True
        )
        member_count = group_info.get("member_count", 0)
        min_size = self.cfg.min_group_size

        # 1. 小群限制
        if self.cfg.block_small_group and member_count <= min_size:
            result.admin_reply += self._suffix(
                "invited_small_group",
                member_count=member_count,
                min_size=min_size,
                **ctx,
            )
            result.operator_reply = self._reply(
                "invited_small_group",
                "operator",
                member_count=member_count,
                min_size=min_size,
            )
            result.leave_group = True
            return True

        # 2. 大群限制
        max_size = self.cfg.max_group_size
        if max_size and member_count > max_size:
            result.admin_reply += self._suffix(
                "invited_large_group",
                member_count=member_count,
                max_size=max_size,
                **ctx,
            )
            result.operator_reply = self._reply(
                "invited_large_group",
                "operator",
                member_count=member_count,
                max_size=max_size,
            )
            result.leave_group = True
            return True

        return False


# =========================
# 应用层（唯一入口）
# =========================
class NoticeHandle:
    def __init__(self, forward: ForwardHandle, config: PluginConfig):
        self.forward = forward
        self.cfg = config

    def need_handle(self, msg: NoticeMessage) -> bool:
        return (
            msg.post_type == "notice"
            and msg.user_id == msg.self_id
            and msg.operator_id != msg.self_id
        )

    async def on_notice(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", {})
        msg = NoticeMessage.from_raw(raw)

        if not self.need_handle(msg):
            return

        client = event.bot
        service = NoticeDecisionService(client, msg, self.cfg)
        result = await service.decide()

        # 操作者提示
        if result.operator_reply:
            await event.send(event.plain_result(result.operator_reply))

        # 管理者提示
        if result.admin_reply:
            if self.cfg.manage_group:
                await event.bot.send_group_msg(
                    group_id=int(self.cfg.manage_group),
                    message=result.admin_reply,
                )
            elif self.cfg.admin_id:
                await event.bot.send_private_msg(
                    user_id=int(self.cfg.admin_id), message=result.admin_reply
                )

        # 延时抽查
        if result.delay_check and self.cfg.check_delay > 0:
            await asyncio.sleep(self.cfg.check_delay)

        if (
            self.cfg.auto_check_messages
            and (result.admin_reply or result.operator_reply)
            and (self.cfg.manage_group or self.cfg.admin_id)
        ):
            fgid = int(self.cfg.manage_group) if self.cfg.manage_group else None
            fuid = int(self.cfg.admin_id) if self.cfg.admin_id else None
            await self.forward.source_forward(
                client=event.bot,
                count=self.cfg.msg_check_count,
                source_group_id=int(event.get_group_id()),
                source_user_id=int(event.get_sender_id()),
                forward_group_id=fgid,
                forward_user_id=fuid,
            )

        # 黑名单副作用
        if result.add_group_blacklist:
            if msg.group_id not in self.cfg.group_blacklist:
                self.cfg.group_blacklist.append(msg.group_id)
                self.cfg.save()
                logger.info(f"群聊 {msg.group_id} 已加入黑名单")

        # 退群
        if result.leave_group:
            await asyncio.sleep(5)
            await client.set_group_leave(group_id=int(msg.group_id))

        event.stop_event()
