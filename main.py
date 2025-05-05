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
    "1.0.3",
    "https://github.com/Zhalslar/astrbot_plugin_relationship",
)
class Relationship(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.manage_group: int = config.get("manage_group", 0)
        self.admins_id =  AstrBotConfig().get("admins_id")


    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("群列表")
    async def show_groups_info(self, event: AiocqhttpMessageEvent):
        """查看加入的所有群聊信息"""
        client = event.bot
        group_list = await client.get_group_list()
        group_info = "\n".join(
            f"{g['group_id']}: {g['group_name']}" for g in group_list
        )
        info = f"【群列表】共加入{len(group_list)}个群：\n{group_info}"
        yield event.plain_result(info)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("好友列表")
    async def show_friends_info(self, event: AiocqhttpMessageEvent):
        """查看所有好友信息"""
        client = event.bot
        friend_list = await client.get_friend_list()
        friend_info = "\n".join(f"{f['user_id']}: {f['nickname']}" for f in friend_list)
        info = f"【好友列表】共{len(friend_list)}位好友：\n{friend_info}"
        yield event.plain_result(info)

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
        client = event.bot
        notice = ""
        #print(event.message_obj)
        if not hasattr(event, "message_obj") or not hasattr(
            event.message_obj, "raw_message"
        ):
            return
        raw_message = event.message_obj.raw_message
        # 处理 raw_message
        if not raw_message or not isinstance(raw_message, dict):
            return
        # 确保是 request 类型的消息
        if raw_message.get("post_type") != "request":
            return

        # 加好友事件
        if raw_message.get("request_type") == "friend":
            user_id = raw_message.get("user_id", "")
            comment = raw_message.get("comment") or "无"
            flag = raw_message.get("flag")
            nickname = (await client.get_stranger_info(user_id=int(user_id)))["nickname"] or "未知昵称"

            # 通知信息
            notice = (
                f"【收到好友申请】同意吗："
                f"\n昵称：{nickname}"
                f"\nQQ号：{user_id}"
                f"\nflag：{flag}"
                f"\n验证信息：{comment}"
            )

        # 群邀请事件
        elif raw_message.get("request_type") == "group" and raw_message.get("sub_type") == "invite" :
            user_id = raw_message.get("user_id", "")
            group_id = raw_message.get("group_id", "")
            comment = raw_message.get("comment") or "无"
            flag = raw_message.get("flag")
            nickname = (await client.get_stranger_info(user_id=int(user_id)))["nickname"] or "未知昵称"
            group_name = (await client.get_group_info(group_id=group_id))["group_name"] or "未知群名"

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
            group_list = await client.get_group_list()
            gids = [str(f["group_id"]) for f in group_list]
            if str(user_id) in gids:
                yield event.plain_result(f"想要我进群？先进管理群：{self.manage_group}")

        # 反馈管理员（群）
        if self.manage_group:
            await client.send_group_msg(group_id=self.manage_group, message=notice)
        elif self.admins_id:
            for admin_id in self.admins_id:
                await client.send_private_msg(user_id=int(admin_id), message=notice)

        # 反馈用户
        friend_list = await client.get_friend_list()
        uids = [str(f["user_id"]) for f in friend_list]
        if str(user_id) in uids:
            try:
                if self.manage_group:
                    yield event.plain_result(f"想加好友或拉群？要等开发群{self.manage_group}审批哟")
                else:
                    yield event.plain_result("想加好友或拉群？要等bot管理员审批哟")
            except Exception as e:
                logger.error(f"无法反馈用户：{e}")


    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("同意")
    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        reply = await self.approve(
            event=event,
            extra=extra,
            approve=True
        )
        yield event.plain_result(reply)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("拒绝")
    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        reply = await self.approve(
            event=event,
            extra=extra,
            approve=False
        )
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
        client=event.bot
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

