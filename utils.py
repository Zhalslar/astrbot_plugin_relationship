from aiocqhttp import CQHttp

from astrbot.core.message.components import At, Plain, Reply
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


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

    units = [
        (days, "天"),
        (hours, "小时"),
        (minutes, "分钟"),
        (seconds, "秒"),
    ]

    # 如果只有一个单位非零，直接返回该单位
    non_zero = [(value, label) for value, label in units if value > 0]
    if len(non_zero) == 1:
        value, label = non_zero[0]
        return f"{value}{label}"

    # 否则拼接所有非零单位
    return "".join(f"{value}{label}" for value, label in non_zero)


async def get_user_name(client: CQHttp, user_id: int, group_id: int = 0) -> str:
    """
    获取群成员的昵称或群名片，无法获取则返回“未知用户”
    """
    if user_id == 0:
        return "未知"
    if group_id:
        name = (
            await client.get_group_member_info(group_id=group_id, user_id=user_id)
        ).get("card")
        if name:
            return name
    name = (await client.get_stranger_info(user_id=user_id)).get("nickname")
    return name or "未知"


def get_reply_text(event: AiocqhttpMessageEvent) -> str:
    """
    获取引用消息的文本
    """
    text = ""
    chain = event.get_messages()
    reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
    if reply_seg and reply_seg.chain:
        for seg in reply_seg.chain:
            if isinstance(seg, Plain):
                text = seg.text
    return text


def get_at_id(event: AiocqhttpMessageEvent):
    """
    获取@的ID
    """
    return next(
        (
            int(seg.qq)
            for seg in event.get_messages()
            if (isinstance(seg, At)) and event.get_sender_id() != event.get_self_id()
        ),
        None,
    )
