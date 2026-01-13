from dataclasses import dataclass

from aiocqhttp import ActionFailed, CQHttp

from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .utils import get_ats, get_nickname, get_reply_text

try:
    from ..afdian import afdian_verify

    _AFDIAN_OK = True
except ImportError:
    _AFDIAN_OK = False


@dataclass
class FriendRequest:
    """好友申请数据类"""

    nickname: str
    user_id: str
    flag: str
    comment: str

    HEADER = "【好友申请】同意/拒绝："

    FIELD_MAP = {
        "昵称": "nickname",
        "QQ号": "user_id",
        "flag": "flag",
        "验证信息": "comment",
    }

    def to_display_text(self) -> str:
        lines = [self.HEADER]
        for cn, field in self.FIELD_MAP.items():
            lines.append(f"{cn}：{getattr(self, field)}")
        return "\n".join(lines)

    @classmethod
    def from_display_text(cls, text: str) -> "FriendRequest | None":
        if cls.HEADER not in text:
            return None

        kwargs = {}
        for line in text.splitlines():
            line = line.strip()
            if "：" not in line:
                continue

            key, _, val = line.partition("：")
            field = cls.FIELD_MAP.get(key)
            if field:
                kwargs[field] = val.strip()

        # comment 可缺省，其余必须存在
        required = set(cls.FIELD_MAP.values()) - {"comment"}
        if not required <= kwargs.keys():
            return None

        kwargs.setdefault("comment", "无")
        return cls(**kwargs)


@dataclass
class GroupRequest:
    inviter_nickname: str
    inviter_id: str
    group_name: str
    group_id: str
    flag: str
    comment: str

    FIELD_MAP = {
        "邀请人昵称": "inviter_nickname",
        "邀请人QQ": "inviter_id",
        "群名称": "group_name",
        "群号": "group_id",
        "flag": "flag",
        "验证信息": "comment",
    }

    HEADER = "【群邀请】同意/拒绝："

    def to_display_text(self) -> str:
        lines = [self.HEADER]
        for cn, field in self.FIELD_MAP.items():
            lines.append(f"{cn}：{getattr(self, field)}")
        return "\n".join(lines)

    @classmethod
    def from_display_text(cls, text: str) -> "GroupRequest | None":
        if cls.HEADER not in text:
            return None

        kwargs = {}
        for line in text.splitlines():
            line = line.strip()
            if "：" not in line:
                continue

            key, _, val = line.partition("：")
            field = cls.FIELD_MAP.get(key)
            if field:
                kwargs[field] = val.strip()

        # comment 允许缺省，其余必须齐全
        required = set(cls.FIELD_MAP.values()) - {"comment"}
        if not required <= kwargs.keys():
            return None

        kwargs.setdefault("comment", "无")
        return cls(**kwargs)


def parse_request_from_text(text: str):
    for cls in (FriendRequest, GroupRequest):
        obj = cls.from_display_text(text)
        if obj:
            return obj
    return None


async def monitor_add_request(
    client: CQHttp, raw_message: dict, config: PluginConfig
) -> tuple[str, str, FriendRequest | GroupRequest | None]:
    """监听好友申请或群邀请

    Returns:
        tuple[str, str, FriendRequest | GroupInvite | None]:
            (admin_reply, user_reply, request_data)
    """
    admin_reply, user_reply = "", ""
    request_data: FriendRequest | GroupRequest | None = None

    user_id: int = raw_message.get("user_id", 0)
    info = await client.get_stranger_info(user_id=int(user_id)) or {}
    nickname = info.get("nickname") or "未知昵称"
    comment: str = raw_message.get("comment") or "无"
    flag = raw_message.get("flag", "")

    # afdian
    afdian_approve = False
    if _AFDIAN_OK and afdian_verify(remark=str(user_id)):
        afdian_approve = True

    # ─────────────────────────────
    # 好友申请
    # ─────────────────────────────
    if raw_message.get("request_type") == "friend":
        request_data = FriendRequest(
            nickname=nickname,
            user_id=str(user_id),
            flag=flag,
            comment=comment,
        )
        admin_reply = request_data.to_display_text()

        if afdian_approve:
            try:
                await client.set_friend_add_request(flag=flag, approve=True)
                admin_reply += "\nAfdian_verify: approved!"
            except ActionFailed as e:
                logger.warning(f"自动审批好友失败: {e}")
        else:
            user_reply = "好友申请已收到，正在审核中，请耐心等待"

    # ─────────────────────────────
    # 群邀请
    # ─────────────────────────────
    elif (
        raw_message.get("request_type") == "group"
        and raw_message.get("sub_type") == "invite"
    ):
        group_id = raw_message.get("group_id", 0)
        group_info = await client.get_group_info(group_id=group_id)
        group_name = group_info.get("group_name") or "未知群名"

        request_data = GroupRequest(
            inviter_nickname=nickname,
            inviter_id=str(user_id),
            group_name=group_name,
            group_id=group_id,
            flag=flag,
            comment=comment,
        )
        admin_reply = request_data.to_display_text()

        if afdian_approve:
            try:
                await client.set_group_add_request(
                    flag=flag, sub_type="invite", approve=True
                )
                admin_reply += "\nAfdian_verify: approved!"
            except ActionFailed as e:
                logger.warning(f"自动审批群邀请失败: {e}")
        else:
            if config.manage_group:
                user_reply = (
                    f"群邀请已收到，需要在审核群 {config.manage_group} 审批后才能加入"
                )
            else:
                user_reply = "群邀请已收到，需要审核通过后才能加入"

            if str(group_id) in config.group_blacklist:
                admin_reply += (
                    "\n警告: 该群为黑名单群聊，请谨慎通过，若通过则自动移出黑名单"
                )
                user_reply += "\n⚠️该群已被列入黑名单，可能不会通过审核"

    return admin_reply, user_reply, request_data


async def handle_add_request(
    client: CQHttp,
    request_data: FriendRequest | GroupRequest,
    approve: bool,
    extra: str = "",
) -> str | None:
    """处理好友申请或群邀请的主函数

    Args:
        client: CQHttp客户端
        request_data: 好友申请或群邀请数据对象
        approve: 是否同意
        extra: 额外信息（好友备注或拒绝理由）

    Returns:
        str | None: 处理结果消息
    """
    if isinstance(request_data, FriendRequest):
        # 处理好友申请
        friend_list = await client.get_friend_list()
        uids = [str(f["user_id"]) for f in friend_list]
        if request_data.user_id in uids:
            return f"【{request_data.nickname}】已经是我的好友啦"

        try:
            await client.set_friend_add_request(
                flag=request_data.flag, approve=approve, remark=extra
            )
            if not approve:
                return f"已拒绝好友：{request_data.nickname}"
            return f"已同意好友：{request_data.nickname}" + (
                f"\n并备注为：{extra}" if extra else ""
            )

        except ActionFailed as e:
            return f"处理好友申请失败：{str(e)}"
        except Exception as e:
            return f"这条申请处理过了或者格式不对：{str(e)}"

    elif isinstance(request_data, GroupRequest):
        # 处理群邀请
        group_list = await client.get_group_list()
        gids = [str(g["group_id"]) for g in group_list]
        if str(request_data.group_id) in gids:
            return f"我已经在【{request_data.group_name}】里啦"

        try:
            await client.set_group_add_request(
                flag=request_data.flag, sub_type="invite", approve=approve, reason=extra
            )
            if approve:
                return f"已同意群邀请: {request_data.group_name}"
            else:
                return f"已拒绝群邀请: {request_data.group_name}" + (
                    f"\n理由：{extra}" if extra else ""
                )
        except ActionFailed as e:
            return f"处理群邀请失败：{str(e)}"
        except Exception as e:
            return f"这条申请处理过了或者格式不对：{str(e)}"


class RequestHandle:
    def __init__(self, config: PluginConfig):
        self.cfg = config

    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听好友申请或群邀请"""
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict) and raw.get("post_type") == "request":
            admin_reply, user_reply, request_data = await monitor_add_request(
                client=event.bot, raw_message=raw, config=self.cfg
            )
            if user_reply and request_data:
                try:
                    if isinstance(request_data, FriendRequest):
                        await event.bot.send_private_msg(
                            user_id=int(request_data.user_id), message=user_reply
                        )
                    elif isinstance(request_data, GroupRequest):
                        await event.bot.send_group_msg(
                            group_id=int(request_data.group_id), message=user_reply
                        )
                except ActionFailed as e:
                    logger.warning(f"用户回执发送失败（可能未加好友或不在群内）: {e}")
            if admin_reply:
                if self.cfg.manage_group:
                    await event.bot.send_group_msg(
                        group_id=int(self.cfg.manage_group), message=admin_reply
                    )
                elif self.cfg.admin_id:
                    await event.bot.send_private_msg(
                        user_id=int(self.cfg.admin_id), message=admin_reply
                    )

    async def agree(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """同意好友申请或群邀请"""
        if event.get_sender_id() not in self.cfg.manage_users:
            yield event.plain_result("你没权限")
            return
        text = get_reply_text(event)
        request_data = parse_request_from_text(text)
        if not request_data:
            yield event.plain_result("无法解析申请信息，请确保引用的是正确的申请消息")
            return

        reply = await handle_add_request(
            client=event.bot, request_data=request_data, approve=True, extra=extra
        )
        if reply:
            yield event.plain_result(reply)

        # 如果是群邀请且群在黑名单中，移出黑名单
        if isinstance(request_data, GroupRequest):
            group_id = str(request_data.group_id)
            if group_id in self.cfg.group_blacklist:
                self.cfg.group_blacklist.remove(group_id)
                self.cfg.save()

    async def refuse(self, event: AiocqhttpMessageEvent, extra: str = ""):
        """拒绝好友申请或群邀请"""
        if event.get_sender_id() not in self.cfg.manage_users:
            await event.send(event.plain_result("你没权限"))
            return

        text = get_reply_text(event)
        request_data = parse_request_from_text(text)
        if not request_data:
            yield event.plain_result("无法解析申请信息，请确保引用的是正确的申请消息")
            return

        reply = await handle_add_request(
            client=event.bot, request_data=request_data, approve=False, extra=extra
        )
        if reply:
            yield event.plain_result(reply)

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
            if at_id in self.cfg.manage_users:
                yield event.plain_result(f"{nickname}已在审批员列表中")
                continue
            self.cfg.manage_users.append(at_id)
            yield event.plain_result(f"已添加审批员: {nickname}")
        self.cfg.save()

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
            if at_id not in self.cfg.manage_users:
                yield event.plain_result(f"{nickname}不在审批员列表中")
                continue
            self.cfg.manage_users.remove(at_id)
            yield event.plain_result(f"已移除审批员: {nickname}")
        self.cfg.save()
