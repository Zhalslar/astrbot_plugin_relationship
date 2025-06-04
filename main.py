import asyncio
from aiocqhttp import CQHttp
from astrbot import logger
from astrbot.api.event import filter
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType


@register(
    "astrbot_plugin_relationship",
    "Zhalslar",
    "[仅aiocqhttp] bot人际关系管理器！包括查看好友列表、查看群列表、审批好友申请、审批群邀请、删好友、退群",
    "1.0.7",
    "https://github.com/Zhalslar/astrbot_plugin_relationship",
)
class Relationship(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 管理群
        self.manage_group: int = config.get("manage_group", 0)
        # 管理员列表
        self.admins_id: list[str] = context.get_config().get("admins_id", [])
        self.admins_id.extend(config.get("admins_id", []))
        self.admins_id=list(set(self.admins_id))
        # 允许的最大禁言时间（秒）
        self.max_ban_duration: int = config.get("max_ban_duration", 86400)
        # 群聊黑名单
        self.group_blacklist: list[str] = config.get("group_blacklist", [])
        # 互斥成员
        self.mutual_blacklist: list[str] = config.get("mutual_blacklist", [])
        # 最大群容量
        self.max_group_capacity: int = config.get("max_group_capacity", 100)
        # 是否自动抽查群聊天记录
        self.auto_check_messages: bool = config.get("auto_check_messages", False)

    @staticmethod
    def convert_duration(duration):
        """格式化时间"""
        days = duration // 86400
        hours = (duration % 86400) // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        result = []
        if days > 0:
            result.append(f"{days}天")
        if hours > 0:
            result.append(f"{hours}小时")
        if minutes > 0:
            result.append(f"{minutes}分钟")
        if seconds > 0 or not result:
            result.append(f"{seconds}秒")

        return " ".join(result)

    async def get_user_name(self, client: CQHttp, group_id: int, user_id: int):
        """获取用户名称"""
        user_info = await client.get_group_member_info(
            group_id=group_id, user_id=user_id
        )
        user_name = user_info.get("card") or user_info.get("nickname")
        return user_name

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def show_groups_info(self, event: AiocqhttpMessageEvent):
        """查看加入的所有群聊信息"""
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
        """查看所有好友信息"""
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
        """退出指定群聊"""
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
        """删除指定好友"""
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
        notice = ""
        # 加好友事件
        if raw_message.get("request_type") == "friend":
            notice = (
                f"【收到好友申请】同意吗："
                f"\n昵称：{nickname}"
                f"\nQQ号：{user_id}"
                f"\nflag：{flag}"
                f"\n验证信息：{comment}"
            )

        # 群邀请事件
        elif (
            raw_message.get("request_type") == "group"
            and raw_message.get("sub_type") == "invite"
        ):
            group_id = raw_message.get("group_id", "")
            group_name = (await client.get_group_info(group_id=group_id))[
                "group_name"
            ] or "未知群名"
            # 通知信息
            notice = (
                f"【收到群邀请】同意吗："
                f"\n邀请人昵称：{nickname}"
                f"\n邀请人QQ：{user_id}"
                f"\n群名称：{group_name}"
                f"\n群号：{group_id}"
                f"\nflag：{flag}"
                f"\n验证信息：{comment}"
            )

        if notice:
            await self.send_reply(client, notice)

        # 反馈给用户
        friend_list: list[dict] = await client.get_friend_list()  # type: ignore
        friend_ids: list[int] = [f["user_id"] for f in friend_list]
        if user_id in friend_ids:
            reply = (
                f"想加好友或拉群？要等开发群({self.manage_group})审批哟"
                if self.manage_group
                else "想加好友或拉群？要等Bot管理员审批哟"
            )
            try:
                await client.send_private_msg(user_id=int(user_id), message=reply)
            except Exception as e:
                logger.error(f"无法反馈用户：{e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        reply = await self.approve(event=event, extra=extra, approve=True)
        yield event.plain_result(reply)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        reply = await self.approve(event=event, extra=extra, approve=False)
        if reply:
            yield event.plain_result(reply)

    @staticmethod
    async def approve(
        event: AiocqhttpMessageEvent, extra: str = "", approve: bool = True
    ) -> str:
        """处理好友申请或群邀请的主函数"""
        text = ""
        chain = event.get_messages()
        reply_seg = next((seg for seg in chain if isinstance(seg, Comp.Reply)), None)
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Comp.Plain):
                    text = seg.text
        lines = text.split("\n")
        client = event.bot
        reply = ""
        if "【收到好友申请】" in text and len(lines) >= 5:
            nickname = lines[1].split("：")[1]  # 第2行冒号后文本为nickname
            uid = lines[2].split("：")[1]  # 第3行冒号后文本为uid
            flag = lines[3].split("：")[1]  # 第4行冒号后文本为flag
            friend_list = await client.get_friend_list()
            uids = [str(f["user_id"]) for f in friend_list]
            if uid in uids:
                reply = f"【{nickname}】已经是我的好友啦"
            else:
                try:
                    await client.set_friend_add_request(
                        flag=flag, approve=approve, remark=extra
                    )
                    if approve:
                        reply = f"已同意好友：{nickname}" + (
                            f"\n并备注为：{extra}" if extra else ""
                        )
                    else:
                        reply = f"已拒绝好友：{nickname}"
                except:  # noqa: E722
                    reply = "这条申请处理过了或者格式不对"

        elif "【收到群邀请】" in text and len(lines) >= 7:
            group_name = lines[3].split("：")[1]  # 第4行冒号后文本为nickname
            gid = lines[4].split("：")[1]  # 第5行冒号后文本为use_id
            flag = lines[5].split("：")[1]  # 第6行冒号后文本为flag
            group_list = await client.get_group_list()
            gids = [str(f["group_id"]) for f in group_list]
            if gid in gids:
                reply = f"我已经在【{group_name}】里啦"
            else:
                try:
                    await client.set_group_add_request(
                        flag=flag, sub_type="invite", approve=approve, reason=extra
                    )
                    if approve:
                        reply = f"已同意群邀请: {group_name}"
                    else:
                        reply = f"已拒绝群邀请: {group_name}" + (
                            f"\n理由：{extra}" if extra else ""
                        )
                except:  # noqa: E722
                    reply = "这条申请处理过了或者格式不对"

        return reply

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """监听事件"""
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
        if operator_id == 0:
            operator_name = "未知"
        else:
            operator_name = await self.get_user_name(client, group_id, operator_id)

        # 是否已成功通知
        is_noticed = False

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
            is_noticed = True
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
                    f"呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{self.convert_duration(duration)}",
                )

            if duration > self.max_ban_duration:
                await self.send_reply(
                    client,
                    f"\n禁言时间超过{self.convert_duration(self.max_ban_duration)}，我退群了",
                )
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)
            is_noticed = True

        # 群成员减少事件
        elif (
            raw_message.get("notice_type") == "group_decrease"
            and raw_message.get("sub_type") == "kick_me"
        ):
            reply = f"呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单"
            self.group_blacklist.append(group_id)
            self.config.save_config()
            await self.send_reply(client, reply)
            is_noticed = True

        # 群成员增加事件
        elif (
            raw_message.get("notice_type") == "group_increase"
            and raw_message.get("sub_type") == "invite"
        ):
            await self.send_reply(
                client, f"主人..我被 {operator_name} 拉进了 {group_name}({group_id})"
            )
            group_list = await client.get_group_list()

            mutual_blacklist_set = set(self.mutual_blacklist.copy())  # 复制并创建新集合
            mutual_blacklist_set.discard(self_id)  # 移除自己的ID
            member_list = await client.get_group_member_list(group_id=group_id)
            member_ids: list[str] = [str(member["user_id"]) for member in member_list]
            common_ids: set[str] = set(member_ids) & mutual_blacklist_set

            # 如果是黑名单里的群，则退群
            if group_id in self.group_blacklist:
                await self.send_reply(
                    client, f"群聊 {group_name}({group_id}) 在黑名单里，我退群了"
                )
                yield event.plain_result("本群在我的黑名单里，我退了")
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            # 如果群容量超过最大群容量，则退群
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

            # 如果群内存在互斥成员，则退群
            elif common_ids:
                user_id = common_ids.pop()  # 获取一个互斥成员
                member_name = await self.get_user_name(client, group_id, int(user_id))
                await self.send_reply(
                    client,
                    f"检测到群内存在互斥成员 {member_name}({user_id})，这群我退了",
                )
                yield event.plain_result(
                    f"我不想和{member_name}({user_id})在同一个群里，退了"
                )
                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)
            is_noticed = True

        # 自动抽查群聊天记录
        if is_noticed and self.auto_check_messages:
            await self.check_messages(client, group_id)

        # 停止事件传播
        if is_noticed:
            event.stop_event()

    async def send_reply(self, client: CQHttp, message: str):
        """发送回复消息"""

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
        self, client: CQHttp, target_group_id: int, notice_group_id: int | None = None
    ):
        """
        抽查指定群聊的消息
        """
        # 获取群聊历史消息
        result: dict = await client.get_group_msg_history(group_id=target_group_id)
        messages: list[dict] = result["messages"]

        # 转换成转发节点(TODO forward消息段的解析待优化)
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

        # 发送
        if notice_group_id or self.manage_group:
            await client.send_group_forward_msg(
                group_id=int(notice_group_id or self.manage_group), messages=nodes
            )
        elif self.admins_id:
            for admin_id in self.admins_id:
                if admin_id.isdigit():
                    await client.send_private_forward_msg(
                        user_id=int(admin_id), messages=nodes
                    )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages_handle(
        self, event: AiocqhttpMessageEvent, target_group_id: int
    ):
        """
        抽查指定群聊的消息
        """
        try:
            await self.check_messages(
                client=event.bot,
                target_group_id=target_group_id,
                notice_group_id=int(event.get_group_id()),
            )
            event.stop_event()
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"抽查群({target_group_id})消息失败: {e}")
