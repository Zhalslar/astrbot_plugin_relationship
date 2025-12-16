from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .utils import get_ats, parse_multi_input

if TYPE_CHECKING:
    from ..main import RelationshipPlugin


class NormalHandle:
    def __init__(self, plugin: "RelationshipPlugin", config: AstrBotConfig):
        self.plugin = plugin
        self.config = config

    # ---------- 查看群列表 ----------

    async def get_group_list(self, event: AiocqhttpMessageEvent):
        client = event.bot
        group_list = await client.get_group_list()

        info = "\n\n".join(
            f"{i + 1}. {g['group_id']}: {g['group_name']}"
            for i, g in enumerate(group_list)
        )
        text = f"【群列表】共加入 {len(group_list)} 个群：\n\n{info}"
        logger.debug(text)

        url = await self.plugin.text_to_image(text)
        await event.send(event.image_result(url))

    # ---------- 查看好友列表 ----------

    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        client = event.bot
        friend_list = await client.get_friend_list()

        info = "\n\n".join(
            f"{i + 1}. {f['user_id']}: {f['nickname']}"
            for i, f in enumerate(friend_list)
        )
        text = f"【好友列表】共 {len(friend_list)} 位好友：\n\n{info}"
        logger.debug(text)

        url = await self.plugin.text_to_image(text)
        await event.send(event.image_result(url))

    # ---------- 退群（批量 / 区间） ----------

    async def set_group_leave(self, event: AiocqhttpMessageEvent):
        """退群 <序号|群号|区间> [可批量]"""
        client = event.bot
        group_list = await client.get_group_list()

        if not group_list:
            await event.send(event.plain_result("我还没加任何群"))
            return

        raw = event.message_str
        indexes, ids = parse_multi_input(raw, total=len(group_list))

        if not indexes and not ids:
            await event.send(event.plain_result("请输入群序号或群号，可空格分隔"))
            return

        group_map = {str(g["group_id"]): g for g in group_list}
        msgs = []

        # 序号
        for idx in sorted(indexes):
            g = group_list[idx]
            await client.set_group_leave(group_id=int(g["group_id"]))
            msgs.append(f"已退出群聊：{g['group_name']}({g['group_id']})")

        # 群号
        for gid in ids:
            g = group_map.get(gid)
            if not g:
                msgs.append(f"不存在群聊：{gid}")
                continue
            await client.set_group_leave(group_id=int(gid))
            msgs.append(f"已退出群聊：{g['group_name']}({gid})")

        await event.send(event.plain_result("\n".join(msgs)))

    # ---------- 删好友（@ / 批量 / 区间） ----------

    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删好友 <@昵称|QQ|序号|区间> [可批量]"""
        client = event.bot
        friend_list = await client.get_friend_list()

        if not friend_list:
            await event.send(event.plain_result("我还没有好友"))
            return

        # 先处理 @
        user_ids = set(get_ats(event))

        # 再解析文本
        raw = event.message_str
        indexes, ids = parse_multi_input(raw, total=len(friend_list))

        # 序号 → QQ
        for idx in indexes:
            user_ids.add(str(friend_list[idx]["user_id"]))

        # 直接 QQ
        user_ids |= ids

        if not user_ids:
            await event.send(event.plain_result("请 @好友、输入 QQ 号或好友序号"))
            return

        friend_map = {str(f["user_id"]): f for f in friend_list}
        msgs = []

        for uid in sorted(user_ids):
            f = friend_map.get(uid)
            if not f:
                msgs.append(f"不存在好友：{uid}")
                continue

            await client.delete_friend(user_id=int(uid))
            msgs.append(f"已删除好友：{f['nickname']}({uid})")

        await event.send(event.plain_result("\n".join(msgs)))


