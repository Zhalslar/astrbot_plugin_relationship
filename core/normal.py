from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .utils import get_ats, get_nickname

if TYPE_CHECKING:
    from ..main import RelationshipPlugin


class NormalHandle:
    def __init__(self, plugin: "RelationshipPlugin", config: AstrBotConfig):
        self.plugin = plugin
        self.config = config

    async def get_group_list(self, event: AiocqhttpMessageEvent):
        """
        查看机器人已加入的所有群聊信息
        """
        client = event.bot
        group_list = await client.get_group_list()
        group_info = "\n\n".join(
            f"{i + 1}. {g['group_id']}: {g['group_name']}"
            for i, g in enumerate(group_list)
        )
        info = f"【群列表】共加入{len(group_list)}个群：\n\n{group_info}"
        logger.debug(info)
        url = await self.plugin.text_to_image(info)
        await event.send(event.image_result(url))

    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        """
        查看所有好友信息
        """
        client = event.bot
        friend_list = await client.get_friend_list()
        friend_info = "\n\n".join(
            f"{i + 1}. {f['user_id']}: {f['nickname']}"
            for i, f in enumerate(friend_list)
        )
        info = f"【好友列表】共{len(friend_list)}位好友：\n\n{friend_info}"
        logger.debug(info)
        url = await self.plugin.text_to_image(info)
        await event.send(event.image_result(url))

    async def set_group_leave(
        self, event: AiocqhttpMessageEvent, group_id: int | None = None
    ):
        """退群 <群号>"""
        if not group_id:
            await event.send(event.plain_result("要指明退哪个群哟~"))
            return

        client = event.bot
        group_list = await client.get_group_list()

        group_ids = [str(group["group_id"]) for group in group_list]
        if str(group_id) not in group_ids:
            await event.send(event.plain_result("我没加有这个群"))
            return

        await client.set_group_leave(group_id=int(group_id))
        await event.send(event.plain_result(f"已退出群聊：{group_id}"))

    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删了 @好友 @QQ"""
        target_ids = get_ats(event)
        if not target_ids:
            await event.send(event.plain_result("请@要删除的好友或@其QQ号。"))
            return

        client = event.bot
        friend_list = await client.get_friend_list()
        friend_ids = [str(friend["user_id"]) for friend in friend_list]

        msgs = []
        for target_id in target_ids:
            target_name = await get_nickname(
                client=event.bot, group_id=event.get_group_id(), user_id=target_id
            )
            if target_id in friend_ids:
                msgs.append(f"已删除好友: {target_name}({target_id})")
                await client.delete_friend(user_id=target_id)
            else:
                msgs.append(f"不存在好友：{target_name}({target_id})")
        await event.send(event.plain_result("\n".join(msgs)))
