from aiocqhttp import CQHttp

from astrbot.core.config.astrbot_config import AstrBotConfig

try:
    from ..afdian import afdian_verify
    _AFDIAN_OK = True
except ImportError:
    _AFDIAN_OK = False

async def monitor_add_request(client: CQHttp, raw_message: dict, config: AstrBotConfig):
    """监听好友申请或群邀请"""
    admin_reply, user_reply = "", ""
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
        admin_reply = f"【好友申请】同意吗：\n昵称：{nickname}\nQQ号：{user_id}\nflag：{flag}\n验证信息：{comment}"
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

        admin_reply = (
            f"【群邀请】同意吗\n"
            f"邀请人昵称：{nickname}\n"
            f"邀请人QQ：{user_id}\n"
            f"群名称：{group_name}\n"
            f"群号：{group_id}\n"
            f"flag：{flag}\n"
            f"验证信息：{comment}"
        )
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


    return admin_reply, user_reply


async def handle_add_request(
    client: CQHttp, info: str, approve: bool , extra: str = ""
) -> str | None:
    """处理好友申请或群邀请的主函数"""
    lines = info.split("\n")
    if "【好友申请】" in info and len(lines) >= 4:
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
            return f"已同意好友：{nickname}" + (f"\n并备注为：{extra}" if extra else "")

        except:  # noqa: E722
            return "这条申请处理过了或者格式不对"

    elif "【群邀请】" in info and len(lines) >= 6:
        group_name = lines[3].split("：")[1]  # 第4行冒号后文本为nickname
        gid = lines[4].split("：")[1]  # 第5行冒号后文本为use_id
        flag = lines[5].split("：")[1]  # 第6行冒号后文本为flag
        group_list = await client.get_group_list()
        gids = [str(f["group_id"]) for f in group_list]
        if gid in gids:
            return f"我已经在【{group_name}】里啦"

        try:
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
