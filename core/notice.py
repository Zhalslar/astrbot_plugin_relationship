import asyncio

from aiocqhttp import CQHttp

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig

from .utils import convert_duration_advanced, get_nickname


async def handle_notice(
    client: CQHttp, raw_message: dict, config: AstrBotConfig
):
    """
    监听群聊相关事件（如管理员变动、禁言、踢出、邀请等），自动处理并反馈
    """
    admin_reply = ""
    operator_reply = ""
    delay_check = False
    leave_group = False
    user_id = raw_message.get("user_id", 0)
    group_id = raw_message.get("group_id", 0)
    group_info = await client.get_group_info(group_id=group_id)
    group_name = group_info.get("group_name")
    operator_id = raw_message.get("operator_id", 0)
    operator_name = await get_nickname(client, user_id=operator_id, group_id=group_id)

    # 群管理员变动
    if raw_message.get("notice_type") == "group_admin":
        if raw_message.get("sub_type") == "set":
            admin_reply = f"哇！我成为了 {group_name}({group_id}) 的管理员"
            operator_reply = "芜湖~拿到管理了"
        else:
            admin_reply = f"呜呜ww..我在 {group_name}({group_id}) 的管理员被撤了"
            operator_reply = "呜呜ww..干嘛撤掉我管理"

    # 群禁言事件
    elif raw_message.get("notice_type") == "group_ban":
        duration = raw_message.get("duration", 0)
        if duration == 0:
            admin_reply = (
                f"好耶！{operator_name} 在 {group_name}({group_id}) 解除了我的禁言"
            )
            operator_reply = "感谢解禁"
        else:
            admin_reply = f"呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{convert_duration_advanced(duration)}"

        if duration > config["max_ban_duration"]:
            admin_reply += f"\n禁言时间超过{convert_duration_advanced(config['max_ban_duration'])}，我退群了"
            leave_group = True
            await asyncio.sleep(3)
            await client.set_group_leave(group_id=group_id)

    # 群成员减少事件 (被踢)
    elif (
        raw_message.get("notice_type") == "group_decrease"
        and raw_message.get("sub_type") == "kick_me"
    ):
        if group_id not in config["group_blacklist"]:
            config["group_blacklist"].append(group_id)
            config.save_config()
        admin_reply = f"呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单"
        logger.info(f"群聊 {group_id} 已因被踢被加入黑名单。")

    # 群成员增加事件 (被邀请)
    elif (
        raw_message.get("notice_type") == "group_increase"
        and raw_message.get("sub_type") == "invite"
    ):
        admin_reply = (f"主人..我被 {operator_name} 拉进了 {group_name}({group_id})。")

        # 获取当前群列表
        group_list = await client.get_group_list()

        # 互斥成员检查
        mutual_blacklist_set = set(config["mutual_blacklist"]).copy()
        mutual_blacklist_set.discard(str(user_id))
        member_list = await client.get_group_member_list(group_id=group_id)
        member_ids: list[str] = [str(member["user_id"]) for member in member_list]
        common_ids: set[str] = set(member_ids) & mutual_blacklist_set

        # 检查1：如果群在黑名单里，则退群
        if group_id in config["group_blacklist"]:
            admin_reply += f"\n群聊 {group_name}({group_id}) 在黑名单里，我退群了"

            operator_reply= "把我踢了还想要我回来？退了退了"
            leave_group = True

        # 检查2：如果群总数超过最大容量，则退群
        elif len(group_list) > config["max_group_capacity"]:
            admin_reply += f"\n我已经加了{len(group_list)}个群（超过了{config['max_group_capacity']}个），这群我退了"
            operator_reply = f"我最多只能加{config['max_group_capacity']}个群，现在已经加了{len(group_list)}个群，请不要拉我进群了"
            leave_group = True

        # 检查3：如果群内存在互斥成员，则退群
        elif common_ids:
            user_id = common_ids.pop()  # 获取一个互斥成员
            member_name = await get_nickname(
                client, user_id=int(user_id), group_id=group_id
            )
            admin_reply += (
                f"\n检测到群内存在互斥成员 {member_name}({user_id})，这群我退了"
            )
            operator_reply = f"我不想和{member_name}({user_id})在同一个群里，退了"
            leave_group = True

        else:
            # 进群延时抽查
            delay_check = True

    return admin_reply, operator_reply, delay_check, leave_group
