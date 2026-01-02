from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.forward import ForwardHandle
from .core.normal import NormalHandle
from .core.notice import NoticeHandle
from .core.request import RequestHandle


class RelationshipPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._normalize_config()

    def _normalize_config(self) -> None:
        """保证 ID 都是数字，并把管理员自动加入审批员列表。"""
        cfg = self.config

        # 1. 管理员 ID 必须是数字
        admins_id: list[str] = [
            str(i) for i in self.context.get_config().get("admins_id", []) if str(i).isdigit()
        ]
        admin_id: str = admins_id[0] if admins_id else ""
        cfg["admin_id"] = admin_id

        # 2. 审批员列表去重 + 保证数字
        manage_users: set[str] = {str(u) for u in cfg.get("manage_users", []) if str(u).isdigit()}
        if admin_id:                       # 管理员自动加入
            manage_users.add(admin_id)
        cfg["manage_users"] = list(manage_users)

        # 3. 审批群号必须是数字
        manage_group = cfg.get("manage_group", "")
        if not str(manage_group).isdigit():
            cfg["manage_group"] = ""

        # 4. 合法性检查（只警告一次）
        if not cfg["manage_group"] and not cfg["manage_users"]:
            logger.warning("未配置审批群或审批员，将无法发送审批消息")

        # 5. 一次性落盘
        self.config.save_config()

    async def initialize(self):
        self.forward = ForwardHandle(self.config)
        self.normal = NormalHandle(self.config)
        self.request = RequestHandle(self.config)
        self.notice = NoticeHandle(self.forward, self.config)


    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def get_group_list(self, event: AiocqhttpMessageEvent):
        """查看bot加入的所有群聊信息"""
        async for msg in self.normal.get_group_list(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        """查看bot的所有好友信息"""
        async for msg in self.normal.get_friend_list(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("退群")
    async def set_group_leave(self, event: AiocqhttpMessageEvent):
        """退群 <序号|群号|区间> [可批量]"""
        await self.normal.set_group_leave(event)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删好友", alias={"删除好友"})
    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删好友 <@昵称|QQ|序号|区间> [可批量]"""
        await self.normal.delete_friend(event)

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        await self.request.event_monitoring(event)

    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        await self.request.agree(event, extra)

    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        await self.request.refuse(event, extra)

    @filter.command("加审批员")
    async def append_manage_user(self, event: AiocqhttpMessageEvent):
        """加审批员@某人"""
        async for msg in self.request.append_manage_user(event):
            yield msg

    @filter.command("减审批员")
    async def remove_manage_user(self, event: AiocqhttpMessageEvent):
        """减审批员@某人"""
        async for msg in self.request.remove_manage_user(event):
            yield msg

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """
        监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
        """
        await self.notice.on_notice(event)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | None = None,
        count: int = 0,
    ):
        """抽查 [群号|@群友|@QQ] [数量], 抽查聊天记录"""
        async for msg in self.forward.check_messages(event, group_id, count):
            yield msg
