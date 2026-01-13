from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.config import PluginConfig
from .core.forward import ForwardHandle
from .core.normal import NormalHandle
from .core.notice import NoticeHandle
from .core.request import RequestHandle


class RelationshipPlugin(Star):
    """
    关系插件
    """
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(context, config)

    async def initialize(self):
        self.forward = ForwardHandle(self.cfg)
        self.normal = NormalHandle(self.cfg)
        self.request = RequestHandle(self.cfg)
        self.notice = NoticeHandle(self.forward, self.cfg)


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
        async for msg in self.normal.set_group_leave(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删好友", alias={"删除好友"})
    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删好友 <@昵称|QQ|序号|区间> [可批量]"""
        async for msg in self.normal.delete_friend(event):
            yield msg
    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        await self.request.event_monitoring(event)

    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        async for msg in self.request.agree(event, extra):
            yield msg
    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        async for msg in self.request.refuse(event, extra):
            yield msg
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
