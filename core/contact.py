import random
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .utils import get_ats


class ContactHandle:
    def __init__(self, config: PluginConfig):
        self.cfg = config

    # -------- 发送层 --------

    @staticmethod
    async def cqhttp_send(event: AiocqhttpMessageEvent, payload: dict):
        """用 aiocqhttp 发送消息"""
        if event.is_private_chat():
            payload["user_id"] = int(event.get_sender_id())
            action = "send_private_msg"
        else:
            payload["group_id"] = int(event.get_group_id())
            action = "send_group_msg"

        try:
            result = await event.bot.api.call_action(action, **payload)
            event.stop_event()
            return result
        except Exception as e:
            raise Exception(f"发送消息失败: {e}")

    async def send_contact(self, event: AiocqhttpMessageEvent, *, uid=None, gid=None):
        """发送 qq / group contact（二选一）"""
        if uid is not None:
            contact = {"type": "qq", "id": int(uid)}
        elif gid is not None:
            contact = {"type": "group", "id": int(gid)}
        else:
            return

        payload = {"message": [{"type": "contact", "data": contact}]}
        await self.cqhttp_send(event, payload)

    # -------- 解析层 --------

    def parse_targets(self, event: AiocqhttpMessageEvent):
        """解析推荐命令里的 uid / gid"""
        args = event.message_str.partition(" ")[2].strip().split()
        gids, uids = [], []

        for arg in args:
            if arg.isdigit():
                gids.append(arg)
            elif arg.startswith("@") and arg[1:].isdigit():
                uids.append(arg[1:])

        uids.extend(get_ats(event))
        return uids, gids

    # -------- 兜底层 --------

    async def get_random_target(self, client) -> tuple[list[int], list[int]]:
        """当没有目标时，随机补一个"""
        if random.random() < 0.5:
            friend_list = await client.get_friend_list()
            return [random.choice(friend_list)["user_id"]], []
        else:
            group_list = await client.get_group_list()
            return [], [random.choice(group_list)["group_id"]]

    # -------- 主入口 --------

    async def contact(self, event: AiocqhttpMessageEvent):
        """推荐 <群号/@群友/@qq>"""
        client = event.bot

        uids, gids = self.parse_targets(event)
        if not uids and not gids:
            uids, gids = await self.get_random_target(client)

        if uids:
            for uid in uids:
                await self.send_contact(event, uid=uid)
        if gids:
            for gid in gids:
                await self.send_contact(event, gid=gid)
