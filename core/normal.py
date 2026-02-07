from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .utils import get_ats, parse_multi_input, get_nickname


class NormalHandle:
    def __init__(self, config: PluginConfig):
        self.cfg = config

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
        yield event.plain_result(text)

    # ---------- 查看好友列表 ----------

    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        client = event.bot
        friend_list = await client.get_friend_list()

        info = "\n\n".join(
            f"{i + 1}. {f['user_id']}: {f['nickname']}"
            for i, f in enumerate(friend_list)
        )
        text = f"【好友列表】共 {len(friend_list)} 位好友：\n{info}"
        logger.debug(text)
        yield event.plain_result(text)

    # ---------- 退群（批量 / 区间） ----------

    async def set_group_leave(self, event: AiocqhttpMessageEvent):
        """退群 <序号|群号|区间> [可批量]"""
        client = event.bot
        group_list = await client.get_group_list()

        if not group_list:
            yield event.plain_result("我还没加任何群")
            return

        raw = event.message_str
        indexes, ids = parse_multi_input(raw, total=len(group_list))

        if not indexes and not ids:
            yield event.plain_result("请输入群序号或群号，可空格分隔")
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

        yield event.plain_result("\n".join(msgs))

    # ---------- 删好友（@ / 批量 / 区间） ----------

    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删好友 <@昵称|QQ|序号|区间> [可批量]"""
        client = event.bot
        friend_list = await client.get_friend_list()

        if not friend_list:
            yield event.plain_result("我还没有好友")
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
            yield event.plain_result("请 @好友、输入 QQ 号或好友序号")
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

        yield event.plain_result("\n".join(msgs))

    async def append_manage_user(self, event: AiocqhttpMessageEvent):
        """添加审批员"""
        at_ids = get_ats(event)
        if not at_ids:
            yield event.plain_result("需@要添加的审批员")
            return
        for at_id in at_ids:
            nickname = await get_nickname(
                client=event.bot, group_id=event.get_group_id(), user_id=at_id
            )
            if self.cfg.is_manage_user(at_id):
                yield event.plain_result(f"{nickname}已在审批员列表中")
                continue
            self.cfg.add_manage_user(at_id)
            yield event.plain_result(f"已添加审批员: {nickname}")

    async def remove_manage_user(self, event: AiocqhttpMessageEvent):
        """移除审批员"""
        at_ids = get_ats(event)
        if not at_ids:
            yield event.plain_result("需@要移除的审批员")
            return
        for at_id in at_ids:
            nickname = await get_nickname(
                client=event.bot, group_id=event.get_group_id(), user_id=at_id
            )
            if not self.cfg.is_manage_user(at_id):
                yield event.plain_result(f"{nickname}不在审批员列表中")
                continue
            self.cfg.remove_manage_user(at_id)
            yield event.plain_result(f"已移除审批员: {nickname}")
