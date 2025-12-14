import asyncio
from aiocqhttp import CQHttp
from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType
from .utils import convert_duration_advanced, get_reply_text, get_user_name, get_at_id


@register(
    "astrbot_plugin_relationship",
    "Zhalslar",
    "[仅aiocqhttp] 人际关系管理器",
    "v2.0.2",
    "https://github.com/Zhalslar/astrbot_plugin_relationship",
)
class Relationship(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 管理群ID，审批信息会发到此群
        self.manage_group: int = config.get("manage_group", 0)
        # 管理员QQ号列表，审批信息会私发给这些人
        self.admins_id: list[str] = list(set(context.get_config().get("admins_id", [])))
        # 最大允许禁言时长，超过自动退群
        self.max_ban_duration: int = config.get("max_ban_duration", 86400)
        # 群聊黑名单，bot不会再加入这些群
        self.group_blacklist: list[str] = config.get("group_blacklist", [])
        # 互斥成员列表，群内有这些人则自动退群
        self.mutual_blacklist: list[str] = config.get("mutual_blacklist", [])
        # 最大群容量，超过自动退群
        self.max_group_capacity: int = config.get("max_group_capacity", 100)
        # 是否自动抽查群消息
        self.auto_check_messages: bool = config.get("auto_check_messages", False)
        # 新群延迟抽查时间（秒）
        self.new_group_check_delay: int = config.get("new_group_check_delay", 600)

    def is_group_in_blacklist(self, group_id) -> bool:
        # 检查黑名单时兼容字符串和数字
        return any(str(group_id) == str(gid) for gid in self.group_blacklist)

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
        """
        管理员命令：让机器人退出指定群聊
        """
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
    async def delete_friend(
        self, event: AiocqhttpMessageEvent, input_id: int | None = None
    ):
        """
        管理员命令：删除指定好友（可@或输入QQ号）
        """
        target_id: int | None = get_at_id(event) or input_id
        if not target_id:
            yield event.plain_result("请 @ 要删除的好友或提供其QQ号。")
            return

        client = event.bot
        friend_list = await client.get_friend_list()
        friend_ids = [int(friend["user_id"]) for friend in friend_list]
<<<<<<< HEAD
        if target_id not in friend_ids:
            yield event.plain_result("我没加有这个人")
            return
=======
>>>>>>> parent of 45d09a6 (up)

        await client.delete_friend(user_id=target_id)
        yield event.plain_result(
            f"已删除好友：{await get_user_name(client=client, user_id=target_id)}({target_id})"
        )

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        if (
            not isinstance(raw_message, dict)
            or raw_message.get("post_type") != "request"
        ):
            return

        logger.info(f"收到好友申请或群邀请: {raw_message}")
        client = event.bot
        user_id: int = raw_message.get("user_id", 0)
        nickname: str = (await client.get_stranger_info(user_id=int(user_id)))[
            "nickname"
        ] or "未知昵称"
        comment: str = raw_message.get("comment") or "无"
        flag = raw_message.get("flag")

        # 加好友事件
        if raw_message.get("request_type") == "friend":
            notice = f"【收到好友申请】同意吗：\n昵称：{nickname}\nQQ号：{user_id}\nflag：{flag}\n验证信息：{comment}"
            await self.send_reply(client, notice)

        # 群邀请事件
        elif (
            raw_message.get("request_type") == "group"
            and raw_message.get("sub_type") == "invite"
        ):
            group_id = raw_message.get("group_id", 0)
            group_name = (await client.get_group_info(group_id=group_id))[
                "group_name"
            ] or "未知群名"

            notice_to_admin = (
                f"【收到群邀请】同意吗\n"
                f"邀请人昵称：{nickname}\n"
                f"邀请人QQ：{user_id}\n"
                f"群名称：{group_name}\n"
                f"群号：{group_id}\n"
                f"flag：{flag}\n"
                f"验证信息：{comment}"
            )
            if self.is_group_in_blacklist(group_id):
                notice_to_admin += (
                    "\n❗警告: 该群为黑名单群聊，请谨慎通过，若通过则自动移出黑名单"
                )

            reply_to_inviter = (
                "想加好友或拉群？要等审核们审批哟"
                if self.manage_group
                else "想加好友或拉群？要等审核审批哟"
            )
            if self.is_group_in_blacklist(group_id):
                reply_to_inviter += "\n⚠️该群已被列入黑名单，可能不会通过审核。"

            await self.send_reply(client, notice_to_admin)
            try:
                await client.send_private_msg(
                    user_id=int(user_id), message=reply_to_inviter
                )
            except Exception as e:
                logger.error(f"无法向邀请者 {user_id} 发送提示: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """
        管理员命令：同意好友申请或群邀请
        """
        reply = await self.approve(event=event, extra=extra, approve=True)
        if reply:
            yield event.plain_result(reply)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """
        管理员命令：拒绝好友申请或群邀请
        """
        reply = await self.approve(event=event, extra=extra, approve=False)
        if reply:
            yield event.plain_result(reply)


    async def approve(
        self, event: AiocqhttpMessageEvent, extra: str = "", approve: bool = True
    ) -> str | None:
        """处理好友申请或群邀请的主函数"""
        text = get_reply_text(event)
        if not text:
            return "需引用一条好友申请或群邀请"
        lines = text.split("\n")
        client = event.bot
        if "【收到好友申请】" in text and len(lines) >= 5:
            nickname = lines[1].split("：")[1]  # 第2行冒号后文本为nickname
            uid = lines[2].split("：")[1]  # 第3行冒号后文本为uid
            flag = lines[3].split("：")[1]  # 第4行冒号后文本为flag
            friend_list = await client.get_friend_list()
            uids = [str(f["user_id"]) for f in friend_list]
            if uid in uids:
                return f"【{nickname}】已经是我的好友啦"

            try:
                await client.set_friend_add_request(
                    flag=flag, approve=approve, remark=extra
                )
                if not approve:
                    return f"已拒绝好友：{nickname}"
                return f"已同意好友：{nickname}" + (
                    f"\n并备注为：{extra}" if extra else ""
                )

            except:  # noqa: E722
                return "这条申请处理过了或者格式不对"

        elif "【收到群邀请】" in text and len(lines) >= 7:
            group_name = lines[3].split("：")[1]  # 第4行冒号后文本为nickname
            gid = lines[4].split("：")[1]  # 第5行冒号后文本为use_id
            flag = lines[5].split("：")[1]  # 第6行冒号后文本为flag
            group_list = await client.get_group_list()
            gids = [str(f["group_id"]) for f in group_list]
            if gid in gids:
                return f"我已经在【{group_name}】里啦"

            try:
                if approve and gid in self.group_blacklist:
                    self.group_blacklist.remove(gid)
                await client.set_group_add_request(
                    flag=flag, sub_type="invite", approve=approve, reason=extra
                )
                if approve:
                    return f"已同意群邀请: {group_name}"
                else:
                    return f"已拒绝群邀请: {group_name}" + (
                        f"\n理由：{extra}" if extra else ""
                    )
            except:  # noqa: E722
                return "这条申请处理过了或者格式不对"

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """
        监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
        """
        raw_message = getattr(event.message_obj, "raw_message", None)
        self_id = event.get_self_id()

        if (
            not raw_message
            or not isinstance(raw_message, dict)
            or raw_message.get("post_type") != "notice"
            or raw_message.get("user_id", 0) != int(self_id)
        ):
            return

        client = event.bot
        group_id = raw_message.get("group_id", 0)
        group_info = await client.get_group_info(group_id=group_id)
        group_name = group_info.get("group_name")
        operator_id = raw_message.get("operator_id", 0)
        if operator_id == int(self_id):
            return
        operator_name = await get_user_name(
            client, user_id=operator_id, group_id=group_id
        )

        # 群管理员变动
        if raw_message.get("notice_type") == "group_admin":
            if raw_message.get("sub_type") == "set":
                await self.send_reply(
                    client, f"哇！我成为了 {group_name}({group_id}) 的管理员"
                )
            else:
                await self.send_reply(
                    client, f"呜呜ww..我在 {group_name}({group_id}) 的管理员被撤了"
                )

            if self.auto_check_messages:
                await self.check_messages(client, group_id=group_id)
            event.stop_event()

        # 群禁言事件
        elif raw_message.get("notice_type") == "group_ban":
            duration = raw_message.get("duration", 0)
            if duration == 0:
                await self.send_reply(
                    client,
                    f"好耶！{operator_name} 在 {group_name}({group_id}) 解除了我的禁言",
                )
            else:
                await self.send_reply(
                    client,
                    f"呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{convert_duration_advanced(duration)}",
                )
            if self.auto_check_messages:
                await self.check_messages(client, group_id=group_id)

            if duration > self.max_ban_duration:
                await self.send_reply(
                    client,
                    f"禁言时间超过{convert_duration_advanced(self.max_ban_duration)}，我退群了",
                )
                if self.auto_check_messages:
                    await self.check_messages(client, group_id=group_id)
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            event.stop_event()

        # 群成员减少事件 (被踢)
        elif (
            raw_message.get("notice_type") == "group_decrease"
            and raw_message.get("sub_type") == "kick_me"
        ):
            if not self.is_group_in_blacklist(group_id):
                self.group_blacklist.append(group_id)
                self.config.save_config()
                logger.info(f"群聊 {group_id} 已因被踢被加入黑名单。")

            reply = f"呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单"
            await self.send_reply(client, reply)

            if self.auto_check_messages:
                await self.check_messages(client, group_id=group_id)
            event.stop_event()

        # 群成员增加事件 (被邀请)
        elif (
            raw_message.get("notice_type") == "group_increase"
            and raw_message.get("sub_type") == "invite"
        ):
            delay_str = convert_duration_advanced(self.new_group_check_delay)
            await self.send_reply(
                client,
                f"主人..我被 {operator_name} 拉进了 {group_name}({group_id})。\n"
                f"我将在{delay_str}后抽查该群消息",
            )

            # 获取当前群列表
            group_list = await client.get_group_list()

            # 互斥成员检查
            mutual_blacklist_set = set(self.mutual_blacklist.copy())
            mutual_blacklist_set.discard(self_id)
            member_list = await client.get_group_member_list(group_id=group_id)
            member_ids: list[str] = [str(member["user_id"]) for member in member_list]
            common_ids: set[str] = set(member_ids) & mutual_blacklist_set

            # 检查1：如果群在黑名单里，则退群
            if self.is_group_in_blacklist(group_id):
                await self.send_reply(
                    client, f"群聊 {group_name}({group_id}) 在黑名单里，我退群了"
                )
                yield event.plain_result("把我踢了还想要我回来？退了退了")
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            # 检查2：如果群总数超过最大容量，则退群
            elif len(group_list) > self.max_group_capacity:
                await self.send_reply(
                    client,
                    f"我已经加了{len(group_list)}个群（超过了{self.max_group_capacity}个），这群我退了",
                )
                yield event.plain_result(
                    f"我最多只能加{self.max_group_capacity}个群，现在已经加了{len(group_list)}个群，请不要拉我进群了"
                )
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            # 检查3：如果群内存在互斥成员，则退群
            elif common_ids:
                user_id = common_ids.pop()  # 获取一个互斥成员
                member_name = await get_user_name(
                    client, user_id=int(user_id), group_id=group_id
                )
                await self.send_reply(
                    client,
                    f"检测到群内存在互斥成员 {member_name}({user_id})，这群我退了",
                )
                yield event.plain_result(
                    f"我不想和{member_name}({user_id})在同一个群里，退了"
                )
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            if self.auto_check_messages:
                await asyncio.sleep(self.new_group_check_delay)
                await self.check_messages(client, group_id=group_id)

            event.stop_event()

    async def send_reply(self, client: CQHttp, message: str):
        """
        发送回复消息到管理群或管理员私聊
        """

        async def send_to_admins():
            """向所有管理员发送私聊消息"""
            for admin_id in self.admins_id:
                if admin_id.isdigit():
                    try:
                        await client.send_private_msg(
                            user_id=int(admin_id), message=message
                        )
                    except Exception as e:
                        logger.error(f"无法反馈管理员：{e}")

        if self.manage_group:
            try:
                await client.send_group_msg(
                    group_id=int(self.manage_group), message=message
                )
            except Exception as e:
                logger.error(f"无法反馈管理群：{e}")
                await send_to_admins()
        elif self.admins_id:
            await send_to_admins()

    async def check_messages(
        self,
        client: CQHttp,
        group_id: int | str = 0,
        user_id: int | str = 0,
        count: int  = 20,
        reply_group_id: int | str = 0,
        reply_user_id: int | str = 0,
    ) -> bool:
        """
        抽查消息
        """
        result = None
        if group_id:
            result = await client.get_group_msg_history(
                group_id=int(group_id), count=count
            )
        elif user_id:
            result = await client.get_friend_msg_history(
                user_id=int(user_id), count=count
            )

        if not result:
            return False

        messages: list[dict] = result.get("messages", [])

        if not messages:
            return False

        # 构造转发节点
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

        # 按优先级转发到目标
        if reply_group_id:
            await client.send_group_forward_msg(
                group_id=int(reply_group_id), messages=nodes
            )
        elif reply_user_id:
            await client.send_private_forward_msg(
                user_id=int(reply_user_id), messages=nodes
            )
        elif self.manage_group:
            await client.send_group_forward_msg(
                group_id=int(self.manage_group), messages=nodes
            )
        elif self.admins_id:
            for admin_id in self.admins_id:
                if admin_id.isdigit():
                    await client.send_private_forward_msg(
                        user_id=int(admin_id), messages=nodes
                    )
        return True

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages_handle(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | None = None,
        count: int = 20,
    ):
        """
        抽查指定群聊的消息
        """
        if not group_id:
            yield event.plain_result("未指定群号")
            return
        try:
            await self.check_messages(
                client=event.bot,
                group_id=group_id,
                reply_group_id=event.get_group_id(),
                reply_user_id=event.get_sender_id(),
                count=count,
            )
            event.stop_event()
        except Exception as e:
            logger.error(f"抽查群({group_id})消息失败: {e}")
            yield event.plain_result(f"抽查群({group_id})消息失败: {e}")
