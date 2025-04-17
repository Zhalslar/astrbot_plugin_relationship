from astrbot.api.event import filter
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType


@register(
    "astrbot_plugin_relationship",
    "Zhalslar",
    "[仅aiocqhttp] bot人际关系管理器！包括查看好友列表、查看群列表、审批好友申请、审批群邀请、删好友、退群",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_relationship",
)
class Relationship(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def show_groups_info(self, event: AiocqhttpMessageEvent):
        """查看加入的所有群聊信息"""
        client = event.bot
        group_list = await client.get_group_list()
        group_info = "\n".join(
            f"{g['group_id']}: {g['group_name']}" for g in group_list
        )
        info = f"【群列表】共加入{len(group_list)}个群：\n{group_info}"
        yield event.plain_result(info)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def show_friends_info(self, event: AiocqhttpMessageEvent):
        """查看所有好友信息"""
        client = event.bot
        friend_list = await client.get_friend_list()
        friend_info = "\n".join(f"{f['user_id']}: {f['nickname']}" for f in friend_list)
        info = f"【好友列表】共{len(friend_list)}位好友：\n{friend_info}"
        yield event.plain_result(info)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("退群")
    async def set_group_leave(self, event: AiocqhttpMessageEvent, group_id: int|None = None):
        """查看所有好友信息"""
        if not group_id:
            yield event.plain_result("要指明退哪个群哟~")
            return

        client = event.bot
        group_list = await client.get_group_list()

        group_ids = [int(group["group_id"]) for group in group_list]
        if group_id not in group_ids:
            yield event.plain_result("我没加有这个群")
            return

        await client.set_group_leave(group_id=group_id)
        yield event.plain_result(f"已退出群聊：{group_id}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删了", alias={"删除好友"})
    async def delete_friend(self, event: AiocqhttpMessageEvent, input_id: int|None = None):
        """查看所有好友信息"""
        chain = event.get_messages()
        target_id: int = input_id or next(
            int(seg.qq) for seg in chain if (isinstance(seg, Comp.At))
        )

        client = event.bot
        friend_list = await client.get_friend_list()

        friend_ids = [int(friend["user_id"]) for friend in friend_list]
        if target_id not in friend_ids:
            yield event.plain_result("我没加有这个人")
            return

        await client.delete_friend(group_id=target_id)
        yield event.plain_result(f"已删除好友：{target_id}")
