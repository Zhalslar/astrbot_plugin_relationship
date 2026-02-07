from aiocqhttp import CQHttp
from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from ..config import PluginConfig
from .model import FriendRequest, GroupRequest, BaseRequest
from .decision import RequestDecision
from ..utils import get_reply_text
from ..forward import ForwardTool


class RequestHandle:
    def __init__(self, config: PluginConfig):
        self.cfg = config

    async def handle_cmd(
        self,
        event: AiocqhttpMessageEvent,
        approve: bool,
        extra: str = "",
    ):
        """处理好友申请或群邀请"""
        sender_id = event.get_sender_id()
        if not self.cfg.is_manage_user(sender_id):
            yield event.plain_result("你没权限")
            return
        text = get_reply_text(event)
        req = BaseRequest.from_display_text(text)
        if not req:
            yield event.plain_result("无法解析申请信息，请确保引用的是正确的申请消息")
            return
        async for msg in self._handle_req(event, req, approve=approve, extra=extra):
            yield msg

    async def handle_raw(self, event: AiocqhttpMessageEvent):
        raw = getattr(event.message_obj, "raw_message", None)
        req = await BaseRequest.from_raw(event.bot, raw)
        if not req:
            return
        async for msg in self._handle_req(event, req):
            yield msg

    async def _handle_req(
        self,
        event: AiocqhttpMessageEvent,
        req: BaseRequest,
        approve: bool | None = None,
        extra: str = "",
    ):
        decision = RequestDecision(event.bot, req, self.cfg)
        result = await decision.decide(approve=approve, extra=extra)

        if result.approve is not None:
            await self._do_approve(event.bot, req, result.approve)

        if result.event_reply:
            yield event.plain_result(result.event_reply)

        if result.user_reply:
            await self._send_user_reply(event, req, result.user_reply)

        if result.admin_reply:
            await ForwardTool.send_admin(event, self.cfg, result.admin_reply)

        if result.block_group is False and isinstance(req, GroupRequest):
            self.cfg.remove_black_group(req.group_id)

        if result.block_user is False and isinstance(req, FriendRequest):
            self.cfg.remove_block_user(req.user_id)

    async def _do_approve(self, client: CQHttp, req: BaseRequest, approve: bool):
        try:
            if isinstance(req, FriendRequest):
                await client.set_friend_add_request(flag=req.flag, approve=approve)
            if isinstance(req, GroupRequest):
                await client.set_group_add_request(
                    flag=req.flag, sub_type="invite", approve=approve
                )
        except Exception as e:
            logger.error(f"审批失败: {e}")

    async def _send_user_reply(
        self,
        event: AiocqhttpMessageEvent,
        req: BaseRequest,
        text: str,
    ):
        async def _try(coro):
            try:
                await coro
                return True
            except Exception as e:
                logger.warning(f"消息发送失败: {e}")
                return False

        if isinstance(req, FriendRequest):
            if await _try(
                event.bot.send_private_msg(user_id=int(req.user_id), message=text)
            ):
                return
            await _try(event.send(event.plain_result(text)))

        elif isinstance(req, GroupRequest):
            if await _try(
                event.bot.send_group_msg(group_id=int(req.group_id), message=text)
            ):
                return
            if await _try(
                event.bot.send_private_msg(user_id=int(req.inviter_id), message=text)
            ):
                return
            await _try(event.send(event.plain_result(text)))
