import asyncio
from typing import Dict
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
    "[仅aiocqhttp] 人际关系管理器",
    "v2.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_relationship",
)
class Relationship(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 管理群ID，审批信息会发到此群
        self.manage_group: int = config.get("manage_group", 0)
        # 管理员QQ号列表，审批信息会私发给这些人
        self.admins_id: list[str] = context.get_config().get("admins_id", [])
        self.admins_id.extend(config.get("admins_id", []))
        self.admins_id = list(set(self.admins_id))
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
        # 延迟抽查任务调度表
        self.scheduled_checks: Dict[str, asyncio.Task] = {}
        self.default_check_count: int = config.get("default_check_count", 20)
        self.max_check_count: int = config.get("max_check_count", 100)

    @staticmethod
    def convert_duration_advanced(duration: int) -> str:
        """
        将秒数转换为更友好的时长字符串，如“1天2小时3分钟4秒”
        """
        if duration < 0:
            return "未知时长"
        if duration == 0:
            return "0秒"
        days, rem = divmod(duration, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days > 0 and hours == 0 and minutes == 0 and seconds == 0:
            return f"{days}天"
        if days == 0 and hours > 0 and minutes == 0 and seconds == 0:
            return f"{hours}小时"
        if days == 0 and hours == 0 and minutes > 0 and seconds == 0:
            return f"{minutes}分钟"
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if seconds > 0:
            parts.append(f"{seconds}秒")
        return "".join(parts)

    async def get_user_name(self, client: CQHttp, group_id: int, user_id: int):
        """
        获取群成员的昵称或群名片
        """
        user_info = await client.get_group_member_info(
            group_id=group_id, user_id=user_id
        )
        return user_info.get("card") or user_info.get("nickname")

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
        chain = event.get_messages()
        target_id: int = input_id or next(
            (int(seg.qq) for seg in chain if isinstance(seg, Comp.At)), 0
        )
        if not target_id:
            yield event.plain_result("请 @ 要删除的好友或提供其QQ号。")
            return

        client = event.bot
        friend_list = await client.get_friend_list()
        friend_ids = [int(friend["user_id"]) for friend in friend_list]
        if target_id not in friend_ids:
            yield event.plain_result("我没加有这个人")
            return

        await client.delete_friend(user_id=target_id)
        yield event.plain_result(f"已删除好友：{target_id}")

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请 (增加黑名单预警和优化的用户反馈)"""
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

            # 在通知审核员前，先检查是否为黑名单群
            if self.is_group_in_blacklist(group_id):
                notice_to_admin = (
                    f"【收到群邀请 - ⚠️黑名单警告】\n"
                    f"邀请人昵称：{nickname}\n"
                    f"邀请人QQ：{user_id}\n"
                    f"群名称：{group_name}\n"
                    f"群号：{group_id}\n"
                    f"flag：{flag}\n"
                    f"验证信息：{comment}\n"
                    f"❗警告: 该群为黑名单群聊，请谨慎通过。如审核通过，进群后将不会触发自动退群。"
                )
                await self.send_reply(client, notice_to_admin)

                reply_to_inviter = "⚠️该群已被列入黑名单，可能不会通过审核。"
                try:
                    await client.send_private_msg(
                        user_id=int(user_id), message=reply_to_inviter
                    )
                except Exception as e:
                    logger.error(f"无法向邀请者 {user_id} 发送黑名单提示: {e}")
            else:
                notice_to_admin = (
                    f"【收到群邀请】同意吗：\n"
                    f"邀请人昵称：{nickname}\n"
                    f"邀请人QQ：{user_id}\n"
                    f"群名称：{group_name}\n"
                    f"群号：{group_id}\n"
                    f"flag：{flag}\n"
                    f"验证信息：{comment}"
                )
                await self.send_reply(client, notice_to_admin)

        # 只有在邀请的群不是黑名单群的情况下，才向已是好友的用户发送“等待审批”的通用提示
        if not self.is_group_in_blacklist(group_id):
            friend_list: list[dict] = await client.get_friend_list() # type: ignore
            friend_ids: list[int] = [f["user_id"] for f in friend_list]
            if user_id in friend_ids:
                reply = (
                    "想加好友或拉群？要等审核们审批哟"
                    if self.manage_group
                    else "想加好友或拉群？要等审核审批哟"
                )
                try:
                    await client.send_private_msg(user_id=int(user_id), message=reply)
                except Exception as e:
                    logger.error(f"无法反馈用户：{e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """
        管理员命令：同意好友申请或群邀请
        """
        reply = await self.approve(event=event, extra=extra, approve=True)
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

        elif (
            "【收到群邀请】" in text or "【收到群邀请 - ⚠️黑名单警告】" in text
        ) and len(lines) >= 7:
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
        if operator_id == 0:
            operator_name = "未知"
        else:
            operator_name = await self.get_user_name(client, group_id, operator_id)

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
                await self.check_messages(
                    client=client, target_id=str(group_id), is_automated=True
                )
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
                    f"呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{self.convert_duration_advanced(duration)}",
                )

            if duration > self.max_ban_duration:
                group_id_str = str(group_id)
                if group_id_str in self.scheduled_checks:
                    task = self.scheduled_checks.pop(group_id_str)
                    task.cancel()
                    logger.info(
                        f"机器人因禁言超期决定退群 {group_id}，已取消为其安排的延迟抽查任务。"
                    )
                if not self.is_group_in_blacklist(group_id):
                    self.group_blacklist.append(group_id)
                    self.config.save_config()
                    logger.info(f"群聊 {group_id} 已因禁言超期被加入黑名单。")

                await self.send_reply(
                    client,
                    f"禁言时间超过{self.convert_duration_advanced(self.max_ban_duration)}，我已将此群拉黑并退群了",
                )

                if self.auto_check_messages:
                    logger.info(
                        f"因禁言超期退群，正在对群聊 {group_id} 执行最后一次抽查..."
                    )
                    try:
                        await self.check_messages(
                            client=client, target_id=str(group_id), is_automated=True
                        )
                    except Exception as e:
                        logger.error(f"退群前的最后抽查失败: {e}")

                await asyncio.sleep(3)
                await client.set_group_leave(group_id=group_id)

            event.stop_event()

        # 群成员减少事件 (被踢)
        elif (
            raw_message.get("notice_type") == "group_decrease"
            and raw_message.get("sub_type") == "kick_me"
        ):
            group_id_str = str(group_id)
            if group_id_str in self.scheduled_checks:
                task = self.scheduled_checks.pop(group_id_str)
                task.cancel()
                logger.info(
                    f"机器人被踢出群 {group_id}，已取消为其安排的延迟抽查任务。"
                )

            if not self.is_group_in_blacklist(group_id):
                self.group_blacklist.append(group_id)
                self.config.save_config()
                logger.info(f"群聊 {group_id} 已因被踢被加入黑名单。")

            reply = f"呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单"
            await self.send_reply(client, reply)

            if self.auto_check_messages:
                await self.check_messages(
                    client=client, target_id=str(group_id), is_automated=True
                )
            event.stop_event()

        # 群成员增加事件 (被邀请)
        elif (
            raw_message.get("notice_type") == "group_increase"
            and raw_message.get("sub_type") == "invite"
        ):
            delay_str = self.convert_duration_advanced(self.new_group_check_delay)
            await self.send_reply(
                client,
                f"主人..我被 {operator_name} 拉进了 {group_name}({group_id})。\n"
                f"将在 {delay_str} 后自动抽查近期消息。",
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
                yield event.plain_result("本群在我的黑名单里，我退了")
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

            # 自动抽查新群消息（延迟）
            if self.auto_check_messages:
                group_id_str = str(group_id)

                if group_id_str in self.scheduled_checks:
                    logger.info(
                        f"群 {group_id_str} 已有一个正在等待的抽查任务，忽略本次重复的入群事件。"
                    )
                else:

                    async def _delayed_check():
                        logger.info(
                            f"等待 {self.new_group_check_delay} 秒后，开始对新群 {group_id_str} 进行抽查..."
                        )
                        await asyncio.sleep(self.new_group_check_delay)

                        if group_id_str not in self.scheduled_checks:
                            logger.info(
                                f"群 {group_id_str} 的延迟抽查任务已被取消，不再执行。"
                            )
                            return

                        try:
                            # 再次检查机器人是否还在群里，避免报错
                            current_group_list = await client.get_group_list()
                            if not any(
                                str(g["group_id"]) == group_id_str
                                for g in current_group_list
                            ):
                                logger.warning(
                                    f"执行延迟抽查时发现，机器人已不在群聊 {group_id_str} 中，任务中止。"
                                )
                                return

                            success = await self.check_messages(
                                client=client, target_id=group_id_str, is_automated=True
                            )

                            if not success:
                                report_message = "抽查失败，诶，没有消息么……？"
                                await self.send_reply(client, report_message)

                        except Exception as e:
                            logger.error(
                                f"执行对新群 {group_id_str} 的延迟抽查时出错: {e}"
                            )
                            error_report_message = f"❌ 对新群 {group_name}({group_id_str}) 的延迟抽查任务执行失败，详情请查看后台日志。"
                            await self.send_reply(client, error_report_message)
                        finally:
                            self.scheduled_checks.pop(group_id_str, None)

                    task = asyncio.create_task(_delayed_check())
                    self.scheduled_checks[group_id_str] = task
                    logger.info(
                        f"已为新群 {group_id_str} 安排了一个 {self.new_group_check_delay} 秒后的延迟抽查任务。"
                    )

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
        target_id: int | str,
        reply_to_group: int | str | None = None,
        reply_to_user: int | str | None = None,
        is_automated: bool = False,
        count: int = 20,
    ) -> bool:
        """
        抽查消息
        """
        if count > self.max_check_count:
            count = self.max_check_count

        result = None
        if is_automated:
            try:
                result = await client.get_group_msg_history(
                    group_id=int(target_id), count=count
                )
            except Exception as e:
                logger.warning(
                    f"自动抽查群 {target_id} 失败，可能因为机器人已不在群内。错误: {e}"
                )
                return False
        else:
            is_group, is_friend = False, False
            group_list = await client.get_group_list()
            if any(str(g["group_id"]) == str(target_id) for g in group_list):
                is_group = True
            else:
                friend_list = await client.get_friend_list()
                if any(str(f["user_id"]) == str(target_id) for f in friend_list):
                    is_friend = True

            if is_group:
                result = await client.get_group_msg_history(
                    group_id=int(target_id), count=count
                )
            elif is_friend:
                result = await client.get_friend_msg_history(
                    user_id=int(target_id), count=count
                )
            else:
                raise ValueError(f"ID {target_id} 既不是群聊也不是好友")

        if not result or not result.get("messages"):
            return False

        messages: list[dict] = result.get("messages", [])

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
        if reply_to_group:
            await client.send_group_forward_msg(group_id=int(reply_to_group), messages=nodes)
        elif reply_to_user:
            await client.send_private_forward_msg(
                user_id=int(reply_to_user), messages=nodes
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
        target_id: int | None = None,
        count_str: int | None = None,
    ):
        """
        抽查指定群聊的消息
        """
        if not target_id:
            yield event.plain_result("未指定群号")
            return
        final_count = count_str if count_str and 0<= count_str <= self.max_check_count else self.default_check_count

        try:
            await self.check_messages(
                client=event.bot,
                target_id=target_id,
                reply_to_group=event.get_group_id(),
                reply_to_user=event.get_sender_id(),
                count=final_count,
            )
            event.stop_event()
        except Exception as e:
            logger.exception(e)
            yield event.plain_result(f"抽查ID({target_id})消息失败: {e}")

    def is_group_in_blacklist(self, group_id) -> bool:
        # 检查黑名单时兼容字符串和数字
        return any(str(group_id) == str(gid) for gid in self.group_blacklist)
