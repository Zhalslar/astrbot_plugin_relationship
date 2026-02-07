import asyncio
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from ..forward import ForwardTool
from .model import NoticeMessage
from .decision import NoticeDecision


class NoticeHandle:
    def __init__(self, config: PluginConfig):
        self.cfg = config

    async def handle(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", {})
        notice = NoticeMessage.from_raw(raw)

        if not notice.is_self_notice():
            return

        decision = NoticeDecision(event.bot, notice, self.cfg)
        result = await decision.decide()

        # 操作者提示
        if result.operator_reply:
            yield event.plain_result(result.operator_reply)

        # 管理者提示
        if result.admin_reply:
            await ForwardTool.send_admin(event, self.cfg, result.admin_reply)

        # 查群
        if (
            self.cfg.check.check_new_group
            and result.check_group
            and (self.cfg.manage_group or self.cfg.admin_id)
        ):
            # 延迟
            if self.cfg.check.delay > 0:
                await asyncio.sleep(self.cfg.check.delay)
            # 转发
            fgid = int(self.cfg.manage_group) if self.cfg.manage_group else None
            fuid = int(self.cfg.admin_id) if self.cfg.admin_id else None
            await ForwardTool.source_forward(
                client=event.bot,
                count=self.cfg.check.count,
                source_group_id=int(event.get_group_id()),
                source_user_id=int(event.get_sender_id()),
                forward_group_id=fgid,
                forward_user_id=fuid,
            )

        # 拉黑群聊
        if result.black_group:
            self.cfg.add_black_group(notice.group_id)

        # 拉黑用户
        if result.black_user:
            self.cfg.add_block_user(notice.user_id)

        # 退群
        if result.leave_group:
            await asyncio.sleep(5)
            await event.bot.set_group_leave(group_id=int(notice.group_id))

        event.stop_event()
