import asyncio
import random
import re

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.notice import NoticeHandler
from .core.request import (
    handle_add_request,
    monitor_add_request,
)
from .core.utils import (
    check_messages,
    get_ats,
    get_nickname,
    get_reply_text,
)


class RelationshipPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # bot管理员QQ（仅取一位纯数字的）
        self.admin_id: str | None = next(
            (str(i) for i in context.get_config().get("admins_id", []) if i.isdigit()),
            None,
        )
        # 管理群号
        self.manager_group: str = str(self.config["manager_group"])
        if not self.admin_id and self.manager_group:
            raise Exception("Bot管理员QQ、管理群群号不能同时为空, 请至少填写一个")

    async def send_reply(self, event: AiocqhttpMessageEvent, message: str):
        """
        发送回复消息到管理群或管理员私聊
        """
        if self.manager_group:
            event.message_obj.group_id = self.manager_group
        elif self.admin_id:
            event.message_obj.group_id = ""
            event.message_obj.sender.user_id = self.admin_id
        else:
            event.stop_event()
            logger.warning("未配置管理员QQ或管理群群号")
            return
        await event.send(event.plain_result(message))

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def show_groups_info(self, event: AiocqhttpMessageEvent):
        """
        管理员命令：查看机器人已加入的所有群聊信息
        """
        client = event.bot
        group_list = await client.get_group_list()
        group_info = "\n\n".join(
            f"{i + 1}. {g['group_id']}: {g['group_name']}"
            for i, g in enumerate(group_list)
        )
        info = f"【群列表】共加入{len(group_list)}个群：\n\n{group_info}"
        url = await self.text_to_image(info)
        yield event.image_result(url)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def show_friends_info(self, event: AiocqhttpMessageEvent):
        """
        管理员命令：查看所有好友信息
        """
        client = event.bot
        friend_list = await client.get_friend_list()
        friend_info = "\n\n".join(
            f"{i + 1}. {f['user_id']}: {f['nickname']}"
            for i, f in enumerate(friend_list)
        )
        info = f"【好友列表】共{len(friend_list)}位好友：\n\n{friend_info}"
        url = await self.text_to_image(info)
        yield event.image_result(url)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("退群")
    async def set_group_leave(
        self, event: AiocqhttpMessageEvent, group_id: int | None = None
    ):
        """退群 <群号>"""
        if not group_id:
            yield event.plain_result("要指明退哪个群哟~")
            return

        client = event.bot
        group_list = await client.get_group_list()

        group_ids = [str(group["group_id"]) for group in group_list]
        if str(group_id) not in group_ids:
            yield event.plain_result("我没加有这个群")
            return

        await client.set_group_leave(group_id=int(group_id))
        yield event.plain_result(f"已退出群聊：{group_id}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删了", alias={"删除好友"})
    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删了 @好友 @QQ"""
        target_ids = get_ats(event)
        if not target_ids:
            yield event.plain_result("请@要删除的好友或@其QQ号。")
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
        yield event.plain_result("\n".join(msgs))

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw_message, dict) and raw_message.get("post_type") == "request":
            admin_reply, user_reply = await monitor_add_request(
                client=event.bot, raw_message=raw_message, config=self.config
            )
            if user_reply:
                yield event.plain_result(user_reply)
            if admin_reply:
                await self.send_reply(event, admin_reply)
            logger.info(f"收到好友申请或群邀请: {raw_message}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        text = get_reply_text(event)
        if "【好友申请】" not in text and "【群邀请】" not in text:
            yield event.plain_result("需引用一条好友申请或群邀请")
            return
        reply = await handle_add_request(
            client=event.bot, info=text, approve=True, extra=extra
        )
        if reply:
            yield event.plain_result(reply)
        group_id = event.get_group_id()
        if group_id in self.config["group_blacklist"]:
            self.config["group_blacklist"].remove(group_id)
            self.config.save_config()

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        text = get_reply_text(event)
        if "【好友申请】" not in text and "【群邀请】" not in text:
            yield event.plain_result("需引用一条好友申请或群邀请")
            return
        reply = await handle_add_request(
            client=event.bot, info=text, approve=False, extra=extra
        )
        if reply:
            yield event.plain_result(reply)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """
        监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
        """
        raw_message = getattr(event.message_obj, "raw_message", None)
        if (
            isinstance(raw_message, dict)
            and raw_message.get("post_type") == "notice"
            and raw_message.get("user_id") == raw_message.get("self_id")
            and raw_message.get("operator_id") != raw_message.get("self_id")
        ):
            client = event.bot
            # 处理通知
            handler = NoticeHandler(client, raw_message, self.config)
            result = await handler.handle()
            admin_reply, operator_reply, delay_check, leave_group = result

            if operator_reply:
                yield event.plain_result(operator_reply)

            if admin_reply:
                await self.send_reply(event, admin_reply)

            if self.config["check_delay"] and delay_check:
                await asyncio.sleep(self.config["check_delay"])
            # 抽查消息
            if self.config["auto_check_messages"] and (admin_reply or operator_reply):
                if self.config["manager_group"]:
                    await check_messages(
                        client=client,
                        source_group_id=event.get_group_id(),
                        forward_group_id=self.config["manager_group"],
                    )
                else:
                    if self.admin_id:
                        await check_messages(
                            client=client,
                            source_group_id=event.get_group_id(),
                            forward_user_id=self.admin_id,
                        )
            # 退群
            if leave_group:
                await asyncio.sleep(5)
                await client.set_group_leave(group_id=raw_message.get("group_id", 0))
            # 停止事件传播
            event.stop_event()

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages_handle(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | None = None,
        count: int = 20,
    ):
        """抽查指定群聊的消息"""
        client = event.bot

        # 尝试从引用消息中获取群号 (第一串长度 5–10 的连续数字)
        text = get_reply_text(event)
        if not group_id:
            m = re.search(r"\d{5,10}", text)
            group_id = int(m.group(0)) if m else None

        # 未指定群号时，随机获取一个群号
        if not group_id:
            group_list = await client.get_group_list()
            if not group_list:
                yield event.plain_result("未找到可用的群聊，无法进行抽查")
                return
            group_id = random.choice(group_list)["group_id"]

        try:
            await check_messages(
                client=client,
                source_group_id=group_id,
                forward_group_id=event.get_group_id(),
                forward_user_id=event.get_sender_id(),
                count=count,
            )
            event.stop_event()
        except Exception as e:
            yield event.plain_result(f"抽查群({group_id})消息失败")
            logger.error(f"抽查群({group_id})消息失败: {e}")
