from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.config import PluginConfig
from .core.contact import ContactHandle
from .core.forward import ForwardTool
from .core.normal import NormalHandle
from .core.notice import NoticeHandle
from .core.request import RequestHandle
from .core.utils import get_ats, get_nickname


class RelationshipPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.normal = NormalHandle(self.cfg)
        self.request = RequestHandle(self.cfg)
        self.notice = NoticeHandle(self.cfg)
        self.contact = ContactHandle(self.cfg)

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

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("加审批员")
    async def append_manage_user(self, event: AiocqhttpMessageEvent):
        """加审批员@某人"""
        async for msg in self.normal.append_manage_user(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("减审批员")
    async def remove_manage_user(self, event: AiocqhttpMessageEvent):
        """减审批员@某人"""
        async for msg in self.normal.remove_manage_user(event):
            yield msg

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """
        监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
        """
        async for msg in self.notice.handle(event):
            yield msg

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def on_request(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        async for msg in self.request.handle_raw(event):
            yield msg

    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        async for msg in self.request.handle_cmd(event, approve=True, extra=extra):
            yield msg

    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        async for msg in self.request.handle_cmd(event, approve=False, extra=extra):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | None = None,
        count: int | None = None,
    ):
        """抽查 [群号|@群友|@QQ] [数量], 抽查聊天记录"""
        count = count or self.cfg.check.count
        async for msg in ForwardTool.check_messages(
            event,
            target_id=group_id,
            count=count,
        ):
            yield msg

    @filter.command("推荐")
    async def on_contact(self, event: AiocqhttpMessageEvent):
        """推荐 <群号/@群友/@qq>"""
        await self.contact.contact(event)

    @filter.command("加好友")
    async def add_group(self, event: AiocqhttpMessageEvent):
        """加好友 [QQ号/@某人] [验证消息] [备注] [答案]"""
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            yield event.plain_result("该功能仅对开发人员开放")
            return
        parts = event.message_str.strip().split()
        args = parts[1:] if len(parts) > 1 else []
        at_ids = get_ats(event)
        if at_ids:
            target_uin = int(at_ids[0])
            if args:
                args = args[1:]
        elif args:
            try:
                target_uin = int(args[0])
                args = args[1:]
            except ValueError:
                yield event.plain_result("QQ号格式错误")
                return
        else:
            yield event.plain_result("需指定要加谁（QQ号 或 @某人）")
            return
        verify = args[0] if args else ""
        remark = args[1] if len(args) > 1 else ""
        answer = args[2] if len(args) > 2 else ""
        client = event.bot
        self_id = int(event.get_self_id())
        if not verify:
            gid = event.get_group_id()
            group_id = int(gid) if gid else 0
            group_info = await client.get_group_info(group_id=group_id, no_cache=True)
            group_name = group_info.get("group_name", str(group_id))
            self_name = await get_nickname(client, group_id, self_id)
            verify = f"我是来自{group_name}的{self_name}"
        msg = await ExpansionHandle.add_friend(
            client=client,
            target_uin=target_uin,
            self_id=self_id,
            verify=verify,
            remark=remark,
            answer=answer,
        )
        yield event.plain_result(msg)

    @filter.command("加群")
    async def add_friend(self, event: AiocqhttpMessageEvent):
        """加群 [群号] [答案]"""
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            yield event.plain_result("该功能仅对开发人员开放")
            return
        parts = event.message_str.strip().split()
        args = parts[1:] if len(parts) > 1 else []
        if not args:
            yield event.plain_result("用法：加群 群号 [答案]")
            return
        try:
            target_gid = int(args[0])
        except ValueError:
            yield event.plain_result("群号格式错误")
            return
        parts = event.message_str.strip().split()
        args = parts[1:] if len(parts) > 1 else []
        if not args:
            yield event.plain_result("用法：加群 群号 [答案]")
            return
        try:
            target_gid = int(args[0])
        except ValueError:
            yield event.plain_result("群号格式错误")
            return
        answer = args[1] if len(args) > 1 else None
        client = event.bot
        self_id = int(event.get_self_id())
        if not answer:
            gid = event.get_group_id()
            group_id = int(gid) if gid else 0
            sender_name = event.get_sender_name()
            self_name = await get_nickname(client, group_id, self_id)
            answer = f"我是{sender_name}推荐来的{self_name}"
        msg = await ExpansionHandle.add_group(
            client=client, target_gid=target_gid, answer=answer
        )
        yield event.plain_result(msg)
