import random
from typing import Any

from aiocqhttp import CQHttp

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .utils import get_ats, get_reply_text, parse_multi_input


class ForwardHandle:
    def __init__(self, config: AstrBotConfig):
        self.config = config

    def _make_nodes(self, messages: list[dict]) -> list[dict[str, Any]]:
        """消息 -> 转发节点"""
        nodes = []
        for message in messages:
            node = {
                "type": "node",
                "data": {
                    "name": message["sender"]["nickname"],
                    "uin": message["sender"]["user_id"],
                    "content": message["message"],
                },
            }
            nodes.append(node)
        return nodes

    async def _get_msg_history(
        self,
        client: CQHttp,
        count: int,
        group_id: int | None = None,
        user_id: int | None = None,
    ) -> list[dict] | None:
        """调用接口获取消息历史，群消息优先"""
        result = None
        if group_id:
            try:
                result = await client.get_group_msg_history(
                    group_id=group_id, count=count
                )
            except Exception:
                logger.exception(f"获取群({group_id})消息历史失败")
        elif user_id:
            try:
                result = await client.get_friend_msg_history(
                    user_id=user_id, count=count
                )
            except Exception:
                logger.exception(f"获取好友({user_id})消息历史失败")
        return result.get("messages") if result else None

    async def _forward_messages(
        self,
        client: CQHttp,
        messages: list[dict],
        group_id: int | None = None,
        user_id: int | None = None,
        batch_size: int = 0,
    ) -> None:
        """调用接口转发消息，群消息优先（支持分批，batch_size=0 表示不分批）"""
        if batch_size <= 0:
            batch_size = len(messages)

        # 把 messages 切成多批
        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            try:
                if group_id:
                    await client.send_group_forward_msg(
                        group_id=group_id, messages=batch
                    )
                elif user_id:
                    await client.send_private_forward_msg(
                        user_id=user_id, messages=batch
                    )
                logger.debug(f"转发消息成功（第{i // batch_size + 1}批）")
            except Exception:
                logger.exception(f"转发消息失败（第{i // batch_size + 1}批）")

    async def source_forward(
        self,
        client: CQHttp,
        count: int,
        source_group_id: int | None = None,
        source_user_id: int | None = None,
        forward_group_id: int | None = None,
        forward_user_id: int | None = None,
    ) -> bool:
        """
        转发消息
        :param client: CQHttp 实例
        :param count: 转发数量
        :param source_group_id: 源群组ID(优先使用)
        :param source_user_id: 源用户ID
        :param forward_group_id: 转发群组ID(优先使用)
        :param forward_user_id: 转发用户ID
        """
        try:
            # 获取消息历史
            messages = await self._get_msg_history(
                client, group_id=source_group_id, user_id=source_user_id, count=count
            )
            if not messages:
                return False
            # 构造转发节点
            nodes = self._make_nodes(messages)

            # 按优先级转发到目标
            await self._forward_messages(
                client,
                group_id=forward_group_id,
                user_id=forward_user_id,
                messages=nodes,
                batch_size=self.config["batch_size"],
            )
            return True
        except Exception:
            return False

    async def check_messages(
        self,
        event: AiocqhttpMessageEvent,
        target: str | int | None = None,
        count: int = 0,
    ):
        """
        抽查指定群或用户的消息
        支持：
        - @用户
        - 群序号（来自群列表）
        - 群号 / QQ
        """
        client = event.bot
        sgid: int | None = None
        suid: int | None = None
        count = count or self.config["msg_check_count"]

        # 1.优先：@ 用户
        if at_ids := get_ats(event, noself=True):
            suid = int(at_ids[0])

        # 2.文本解析（复用 parse_multi_input）
        if not suid:
            raw = str(target or get_reply_text(event) or "").strip()

            # 先解析可能的序号 / ID
            group_list = await client.get_group_list()
            indexes, ids = parse_multi_input(raw, total=len(group_list))

            # 2.1 序号 → 群
            if indexes:
                idx = min(indexes)
                sgid = int(group_list[idx]["group_id"])

            # 2.2 明确 ID 视为群号
            elif ids:
                value = next(iter(ids))
                if value.isdigit():
                    sgid = int(value)

        # 3.兜底：随机群
        if not sgid and not suid:
            group_list = await client.get_group_list()
            if not group_list:
                yield event.plain_result("未找到可用的群聊或用户，无法进行抽查")
                return
            sgid = int(random.choice(group_list)["group_id"])

        # 执行抽查
        logger.debug(
            f"正在抽查{f'群({sgid})' if sgid else f'用户({suid})'}的 {count} 条聊天记录..."
        )

        try:
            await self.source_forward(
                client=client,
                count=count,
                source_group_id=sgid,
                source_user_id=suid,
                forward_group_id=int(event.get_group_id()),
                forward_user_id=int(event.get_sender_id()),
            )
            event.stop_event()
        except Exception as e:
            yield event.plain_result(f"抽查失败：{e}")
            logger.error(f"抽查失败: {e}")
