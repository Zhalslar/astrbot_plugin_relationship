from dataclasses import dataclass

from aiocqhttp import ActionFailed, CQHttp
from astrbot.core.config.astrbot_config import AstrBotConfig

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

    def to_display_text(self) -> str:
        """转换为展示文本"""
        return (
            f"【好友申请】同意吗：\n"
            f"昵称：{self.nickname}\n"
            f"QQ号：{self.user_id}\n"
            f"flag：{self.flag}\n"
            f"验证信息：{self.comment}"
        )


@dataclass
class GroupInvite:
    """群邀请数据类"""
    inviter_nickname: str
    inviter_id: str
    group_name: str
    group_id: str
    flag: str
    comment: str

    def to_display_text(self) -> str:
        """转换为展示文本"""
        return (
            f"【群邀请】同意吗\n"
            f"邀请人昵称：{self.inviter_nickname}\n"
            f"邀请人QQ：{self.inviter_id}\n"
            f"群名称：{self.group_name}\n"
            f"群号：{self.group_id}\n"
            f"flag：{self.flag}\n"
            f"验证信息：{self.comment}"
        )

async def monitor_add_request(
    client: CQHttp, raw_message: dict, config: AstrBotConfig
) -> tuple[str, str, FriendRequest | GroupInvite | None]:
    """监听好友申请或群邀请
    
    Returns:
        tuple[str, str, FriendRequest | GroupInvite | None]: 
            (admin_reply, user_reply, request_data)
    """
    admin_reply, user_reply = "", ""
    request_data: FriendRequest | GroupInvite | None = None
    
    user_id: int = raw_message.get("user_id", 0)
    nickname: str = (await client.get_stranger_info(user_id=int(user_id)))[
        "nickname"
    ] or "未知昵称"
    comment: str = raw_message.get("comment") or "无"
    flag = raw_message.get("flag", "")

    # afdian
    afdian_approve = False
    if _AFDIAN_OK and afdian_verify(remark=str(user_id)):
        afdian_approve = True

    # 加好友事件
    if raw_message.get("request_type") == "friend":
        request_data = FriendRequest(
            nickname=nickname,
            user_id=str(user_id),
            flag=flag,
            comment=comment
        )
        admin_reply = request_data.to_display_text()
        
        if afdian_approve:
            await client.set_friend_add_request(flag=flag, approve=True)
            admin_reply += "\nAfdian_verify: approved!"

    # 群邀请事件
    elif (
        raw_message.get("request_type") == "group"
        and raw_message.get("sub_type") == "invite"
    ):
        group_id = raw_message.get("group_id", 0)
        group_name = (await client.get_group_info(group_id=group_id))[
            "group_name"
        ] or "未知群名"

        request_data = GroupInvite(
            inviter_nickname=nickname,
            inviter_id=str(user_id),
            group_name=group_name,
            group_id=str(group_id),
            flag=flag,
            comment=comment
        )
        admin_reply = request_data.to_display_text()
        
        if afdian_approve:
            await client.set_group_add_request(
                flag=flag, sub_type="invite", approve=True
            )
            admin_reply += "\nAfdian_verify: approved!"
        else:
            if config["manager_group"]:
                user_reply = f"想加好友或拉群？要等审核群{config['manager_group']}审批哟"
            else:
                user_reply = "想加好友或拉群？要等审核通过哦"

            if str(group_id) in config["group_blacklist"]:
                admin_reply += (
                    "\n警告: 该群为黑名单群聊，请谨慎通过，若通过则自动移出黑名单"
                )
                user_reply += "\n⚠️该群已被列入黑名单，可能不会通过审核。"

    return admin_reply, user_reply, request_data


async def handle_add_request(
    client: CQHttp, request_data: FriendRequest | GroupInvite, approve: bool, extra: str = ""
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
            return f"已同意好友：{request_data.nickname}" + (f"\n并备注为：{extra}" if extra else "")

        except ActionFailed as e:
            return f"处理好友申请失败：{str(e)}"
        except Exception as e:
            return f"这条申请处理过了或者格式不对：{str(e)}"

    elif isinstance(request_data, GroupInvite):
        # 处理群邀请
        group_list = await client.get_group_list()
        gids = [str(f["group_id"]) for f in group_list]
        if request_data.group_id in gids:
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
    
    return None


def parse_request_from_text(text: str) -> FriendRequest | GroupInvite | None:
    """从文本解析请求数据（向后兼容）
    
    Args:
        text: 包含请求信息的文本
    
    Returns:
        FriendRequest | GroupInvite | None: 解析出的请求数据对象，失败返回None
    """
    lines = text.split("\n")
    
    # 解析好友申请
    if "【好友申请】" in text and len(lines) >= 4:
        try:
            nickname = lines[1].split("：", 1)[1]  # 第2行冒号后文本为nickname
            user_id = lines[2].split("：", 1)[1]  # 第3行冒号后文本为user_id
            flag = lines[3].split("：", 1)[1]  # 第4行冒号后文本为flag
            comment = lines[4].split("：", 1)[1] if len(lines) >= 5 else "无"
            
            return FriendRequest(
                nickname=nickname,
                user_id=user_id,
                flag=flag,
                comment=comment
            )
        except (IndexError, ValueError):
            return None
    
    # 解析群邀请
    elif "【群邀请】" in text and len(lines) >= 6:
        try:
            inviter_nickname = lines[1].split("：", 1)[1]  # 第2行
            inviter_id = lines[2].split("：", 1)[1]  # 第3行
            group_name = lines[3].split("：", 1)[1]  # 第4行
            group_id = lines[4].split("：", 1)[1]  # 第5行
            flag = lines[5].split("：", 1)[1]  # 第6行
            comment = lines[6].split("：", 1)[1] if len(lines) >= 7 else "无"
            
            return GroupInvite(
                inviter_nickname=inviter_nickname,
                inviter_id=inviter_id,
                group_name=group_name,
                group_id=group_id,
                flag=flag,
                comment=comment
            )
        except (IndexError, ValueError):
            return None
    
    return None
