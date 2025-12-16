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
        # bot管理员
        self.admin_id: str = next(
            (str(i) for i in context.get_config().get("admins_id", []) if i.isdigit()),
            "",
        )
        # 审批员
        self.manage_users = config["manage_users"]
        if self.admin_id not in self.manage_users:
            self.manage_users.append(self.admin_id)
            self.config.save_config()
        # 审批群
        self.manage_group: str = config["manage_group"]

        if not self.manage_group and not self.manage_users:
            logger.warning("未配置审批群或审批员，将无法发送审批消息")

    async def initialize(self):
        self.forward = ForwardHandle(self.config)
        self.normal = NormalHandle(self, self.config)
        self.request = RequestHandle(self, self.config)
        self.notice = NoticeHandle(self, self.config)

    async def manage_send(self, event: AiocqhttpMessageEvent, message: str):
        """
        发送回复消息到管理群或bot管理员
        """
        if self.manage_group:
            event.message_obj.group_id = self.manage_group
        elif self.admin_id:
            event.message_obj.group_id = ""
            event.message_obj.sender.user_id = self.admin_id
        else:
            event.stop_event()
            logger.warning("未配置审批群或bot管理员，已跳过消息发送")
            return
        await event.send(event.plain_result(message))

    async def manage_source_forward(self, event: AiocqhttpMessageEvent):
        """抽查消息发给管理群或bot管理员"""
        if self.manage_group or self.admin_id:
            fgid = int(self.manage_group) if self.manage_group.isdigit() else None
            fuid = int(self.admin_id) if self.admin_id.isdigit() else None
            await self.forward.source_forward(
                client=event.bot,
                count=self.config["msg_check_count"],
                source_group_id=int(event.get_group_id()),
                source_user_id=int(event.get_sender_id()),
                forward_group_id=fgid,
                forward_user_id=fuid,
            )
        else:
            logger.warning("未配置管理群或管理用户, 已跳过消息转发")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def get_group_list(self, event: AiocqhttpMessageEvent):
        """查看bot加入的所有群聊信息"""
        await self.normal.get_group_list(event)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        """查看bot的所有好友信息"""
        await self.normal.get_friend_list(event)

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
