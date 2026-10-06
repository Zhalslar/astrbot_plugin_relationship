from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
from astrbot.core.star.filter.platform_adapter_type import PlatformAdapterType

from .core.config import PluginConfig
from .core.contact import ContactHandle
from .core.forward import ForwardTool
from .core.normal import NormalHandle
from .core.notice import NoticeHandle
from .core.request import RequestHandle
from .core.utils import get_ats, get_nickname


class RelationshipPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.normal = NormalHandle(self.cfg)
        self.request = RequestHandle(self.cfg)
        self.notice = NoticeHandle(self.cfg)
        self.contact = ContactHandle(self.cfg)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def get_group_list(self, event: AiocqhttpMessageEvent):
        """查看bot加入的所有群聊信息"""
        async for msg in self.normal.get_group_list(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def get_friend_list(self, event: AiocqhttpMessageEvent):
        """查看bot的所有好友信息"""
        async for msg in self.normal.get_friend_list(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("退群")
    async def set_group_leave(self, event: AiocqhttpMessageEvent):
        """退群 <序号|群号|区间> [可批量]"""
        async for msg in self.normal.set_group_leave(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删好友", alias={"删除好友"})
    async def delete_friend(self, event: AiocqhttpMessageEvent):
        """删好友 <@昵称|QQ|序号|区间> [可批量]"""
        async for msg in self.normal.delete_friend(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("加审批员")
    async def append_manage_user(self, event: AiocqhttpMessageEvent):
        """加审批员@某人"""
        async for msg in self.normal.append_manage_user(event):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("减审批员")
    async def remove_manage_user(self, event: AiocqhttpMessageEvent):
        """减审批员@某人"""
        async for msg in self.normal.remove_manage_user(event):
            yield msg

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_notice(self, event: AiocqhttpMessageEvent):
        """
        监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
        """
        async for msg in self.notice.handle(event):
            yield msg

    @filter.platform_adapter_type(PlatformAdapterType.AIOCQHTTP)
    async def on_request(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        async for msg in self.request.handle_raw(event):
            yield msg

    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        async for msg in self.request.handle_cmd(event, approve=True, extra=extra):
            yield msg

    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        async for msg in self.request.handle_cmd(event, approve=False, extra=extra):
            yield msg

    @filter.command("拉黑")
    async def block(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝并拉黑好友申请人或邀请群"""
        async for msg in self.request.handle_cmd(
            event, approve=False, extra=extra, block=True
        ):
            yield msg

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("抽查")
    async def check_messages(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | None = None,
        count: int | None = None,
    ):
        """抽查 <群号|@群友|@QQ> <数量>, 抽查聊天记录"""
        count = count or self.cfg.check.count
        async for msg in ForwardTool.check_messages(
            event,
            target_id=group_id,
            count=count,
        ):
            yield msg

    @filter.command("推荐")
    async def on_contact(self, event: AiocqhttpMessageEvent):
        """推荐 <群号/@群友/@qq>"""
        await self.contact.contact(event)

    @filter.command("加好友")
    async def add_group(self, event: AiocqhttpMessageEvent):
        """加好友 [QQ号/@某人] [验证消息] [备注] [答案]"""
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            # yield event.plain_result("该功能仅对开发人员开放")
            return
        parts = event.message_str.strip().split()
        args = parts[1:] if len(parts) > 1 else []
        at_ids = get_ats(event)
        if at_ids:
            target_uin = int(at_ids[0])
            if args:
                args = args[1:]
        elif args:
            try:
                target_uin = int(args[0])
                args = args[1:]
            except ValueError:
                yield event.plain_result("QQ号格式错误")
                return
        else:
            yield event.plain_result("需指定要加谁（QQ号 或 @某人）")
            return
        verify = args[0] if args else ""
        remark = args[1] if len(args) > 1 else ""
        answer = args[2] if len(args) > 2 else ""
        client = event.bot
        self_id = int(event.get_self_id())
        if not verify:
            gid = event.get_group_id()
            group_id = int(gid) if gid else 0
            group_info = await client.get_group_info(group_id=group_id, no_cache=True)
            group_name = group_info.get("group_name", str(group_id))
            self_name = await get_nickname(client, group_id, self_id)
            verify = f"我是来自{group_name}的{self_name}"
        msg = await ExpansionHandle.add_friend(
            client=client,
            target_uin=target_uin,
            self_id=self_id,
            verify=verify,
            remark=remark,
            answer=answer,
        )
        yield event.plain_result(msg)

    @filter.command("加群")
    async def add_group_cmd(self, event: AiocqhttpMessageEvent):
        """加群 [群号] [答案]"""
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            # yield event.plain_result("该功能仅对开发人员开放")
            return
        parts = event.message_str.strip().split()
        args = parts[1:] if len(parts) > 1 else []
        if not args:
            yield event.plain_result("用法：加群 群号 [答案]")
            return
        try:
            target_gid = int(args[0])
        except ValueError:
            yield event.plain_result("群号格式错误")
            return
        answer = args[1] if len(args) > 1 else None
        client = event.bot
        self_id = int(event.get_self_id())
        if not answer:
            gid = event.get_group_id()
            group_id = int(gid) if gid else 0
            sender_name = event.get_sender_name()
            self_name = await get_nickname(client, group_id, self_id)
            answer = f"我是{sender_name}推荐来的{self_name}"
        msg = await ExpansionHandle.add_group(
            client=client, target_gid=target_gid, answer=answer
        )
        yield event.plain_result(msg)

    @filter.llm_tool()
    async def llm_get_group_list(
        self,
        event: AiocqhttpMessageEvent,
        need_auth: bool = False,
    ):
        """
        获取机器人加入的所有群聊列表。
        Args:
            need_auth(bool): 是否要进行鉴权，机器人自行发起填 False，用户发起填 True。
        """
        if need_auth and not event.is_admin():
            return "获取群列表失败: 仅管理员有权限查看群列表。"
        try:
            client = event.bot
            group_list = await client.get_group_list()
            if not group_list:
                return "当前机器人未加入任何群聊。"
            lines = [f"共加入 {len(group_list)} 个群聊:"]
            for i, g in enumerate(group_list):
                lines.append(f"{i + 1}. 群号: {g['group_id']}, 群名: {g.get('group_name', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取群列表失败: {e}"

    @filter.llm_tool()
    async def llm_get_friend_list(
        self,
        event: AiocqhttpMessageEvent,
        need_auth: bool = False,
    ):
        """
        获取机器人的所有好友列表。
        Args:
            need_auth(bool): 是否要进行鉴权，机器人自行发起填 False，用户发起填 True。
        """
        if need_auth and not event.is_admin():
            return "获取好友列表失败: 仅管理员有权限查看好友列表。"
        try:
            client = event.bot
            friend_list = await client.get_friend_list()
            if not friend_list:
                return "当前机器人没有任何好友。"
            lines = [f"共 {len(friend_list)} 位好友:"]
            for i, f in enumerate(friend_list):
                lines.append(f"{i + 1}. QQ: {f['user_id']}, 昵称: {f.get('nickname', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取好友列表失败: {e}"

    @filter.llm_tool()
    async def llm_leave_group(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str = ""
    ):
        """
        让机器人退出指定的群聊。
        Args:
            group_id(string): 要退出的QQ群号，默认为当前群聊。
        """
        if not event.is_admin():
            return "退群失败: 仅管理员有权限执行退群操作。"

        gid = str(group_id).strip() or event.get_group_id() or ""
        if not gid.isdigit():
            return "退群失败: group_id 必须为纯数字群号。"

        try:
            client = event.bot
            await client.set_group_leave(group_id=int(gid))
            return f"成功退出群聊: {gid}"
        except Exception as e:
            return f"退群失败: {e}"

    @filter.llm_tool()
    async def llm_delete_friend(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str
    ):
        """
        删除机器人的指定好友。
        Args:
            user_id(string): 要删除的好友QQ号。
        """
        if not event.is_admin():
            return "删除好友失败: 仅管理员有权限执行删除好友操作。"

        uid = str(user_id).strip()
        if not uid.isdigit():
            return "删除好友失败: user_id 必须为纯数字QQ号。"

        try:
            client = event.bot
            await client.delete_friend(user_id=int(uid))
            return f"成功删除好友: {uid}"
        except Exception as e:
            return f"删除好友失败: {e}"

    @filter.llm_tool()
    async def llm_send_contact_card(
        self,
        event: AiocqhttpMessageEvent,
        target_id: str = "",
        target_type: str = "qq",
    ):
        """
        发送推荐名片（群名片或联系人名片）。
        Args:
            target_id(string): 推荐目标的 QQ 号或群号，为空时随机选择一个好友或群推荐。
            target_type(string): 推荐类型，'qq' 为好友/用户推荐名片，'group' 为群推荐名片。默认为 'qq'。
        """
        try:
            tid = str(target_id).strip()
            if not tid:
                uids, gids = await self.contact._get_random_target(client=event.bot)
                if uids:
                    await self.contact._send_contact(event, uid=uids[0])
                    return f"已成功发送推荐好友名片: {uids[0]}"
                elif gids:
                    await self.contact._send_contact(event, gid=gids[0])
                    return f"已成功发送推荐群名片: {gids[0]}"
                return "没有可推荐的好友或群聊。"

            if not tid.isdigit():
                return "发送推荐名片失败: target_id 必须为纯数字。"

            if target_type.lower() == "group":
                await self.contact._send_contact(event, gid=int(tid))
                return f"已成功发送群推荐名片: {tid}"
            else:
                await self.contact._send_contact(event, uid=int(tid))
                return f"已成功发送用户推荐名片: {tid}"
        except Exception as e:
            return f"发送推荐名片失败: {e}"

    @filter.llm_tool()
    async def llm_add_friend_request(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str,
        verify: str = "",
        remark: str = "",
        answer: str = "",
    ):
        """
        向指定 QQ 用户主动发起添加好友申请。
        Args:
            user_id(string): 目标用户的 QQ 号。
            verify(string): 验证消息文本。为空时自动使用默认问候语。
            remark(string): 添加成功后的备注名。
            answer(string): 针对问题验证的回答文本。
        """
        if not event.is_admin():
            return "发起好友申请失败: 仅管理员有权限操作。"
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            return "发起好友申请失败: 核心拓展模块未加载。"

        uid_str = str(user_id).strip()
        if not uid_str.isdigit():
            return "发起好友申请失败: user_id 必须为纯数字QQ号。"

        target_uin = int(uid_str)
        client = event.bot
        self_id = int(event.get_self_id())

        if not verify:
            gid = event.get_group_id()
            group_id = int(gid) if gid else 0
            group_info = await client.get_group_info(group_id=group_id, no_cache=True)
            group_name = group_info.get("group_name", str(group_id))
            self_name = await get_nickname(client, group_id, self_id)
            verify = f"我是来自{group_name}的{self_name}"

        try:
            msg = await ExpansionHandle.add_friend(
                client=client,
                target_uin=target_uin,
                self_id=self_id,
                verify=verify,
                remark=remark,
                answer=answer,
            )
            return msg
        except Exception as e:
            return f"发起好友申请失败: {e}"

    @filter.llm_tool()
    async def llm_add_group_request(
        self,
        event: AiocqhttpMessageEvent,
        group_id: str,
        answer: str = "",
    ):
        """
        主动向指定 QQ 群发起加群申请。
        Args:
            group_id(string): 目标 QQ 群号。
            answer(string): 加群验证问题的回答文本。为空时自动使用默认问候语。
        """
        if not event.is_admin():
            return "发起加群申请失败: 仅管理员有权限操作。"
        try:
            from .core.expansion import ExpansionHandle
        except ImportError:
            return "发起加群申请失败: 核心拓展模块未加载。"

        gid_str = str(group_id).strip()
        if not gid_str.isdigit():
            return "发起加群申请失败: group_id 必须为纯数字群号。"

        target_gid = int(gid_str)
        client = event.bot
        self_id = int(event.get_self_id())

        if not answer:
            gid = event.get_group_id()
            group_id_val = int(gid) if gid else 0
            sender_name = event.get_sender_name()
            self_name = await get_nickname(client, group_id_val, self_id)
            answer = f"我是{sender_name}推荐来的{self_name}"

        try:
            msg = await ExpansionHandle.add_group(
                client=client,
                target_gid=target_gid,
                answer=answer,
            )
            return msg
        except Exception as e:
            return f"发起加群申请失败: {e}"

    @filter.llm_tool()
    async def llm_check_messages(
        self,
        event: AiocqhttpMessageEvent,
        target_id: str = "",
        count: int | None = None,
    ):
        """
        抽查指定群聊或用户的历史聊天记录并以合并转发形式发送到当前会话。
        Args:
            target_id(string): 目标QQ群号或用户QQ号，留空时随机挑选一个群抽查。
            count(number): 抽查消息数量，留空则使用默认配置的抽查数量。
        """
        if not event.is_admin():
            return "抽查失败: 仅管理员有权限执行抽查操作。"

        tid = str(target_id).strip() or None
        target_count = count or self.cfg.check.count
        try:
            async for _ in ForwardTool.check_messages(
                event,
                target_id=tid,
                count=target_count,
            ):
                pass
            return "抽查任务已执行完成，合并转发消息已发送。"
        except Exception as e:
            return f"抽查失败: {e}"
