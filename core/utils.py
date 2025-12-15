
import re

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


async def get_nickname(client: CQHttp, group_id: int | str,  user_id: int | str) -> str:
    """获取指定群友的群昵称或 Q 名，群接口失败/空结果自动降级到陌生人资料"""
    user_id = int(user_id)

    info = {}

    # 在群里就先试群资料，任何异常或空结果都跳过
    if str(group_id).isdigit():
        try:
            info = (
                await client.get_group_member_info(
                    group_id=int(group_id), user_id=user_id
                )
                or {}
            )
        except Exception:
            pass

    # 群资料没拿到就降级到陌生人资料
    if not info:
        try:
            info = await client.get_stranger_info(user_id=user_id) or {}
        except Exception:
            pass

    # 依次取群名片、QQ 昵称、通用 nick，兜底数字 UID
    return info.get("card") or info.get("nickname") or info.get("nick") or str(user_id)


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


def get_ats(
    event: AiocqhttpMessageEvent,
    noself: bool = False,
    block_ids: list[str] | None = None,
    skip_first_seg: bool = True,
):
    """
    获取被at者们的id列表(@增强版)
    Args:
        event: 消息事件对象
        noself: 是否排除自己
        block_ids: 要排除的id列表
        skip_first_seg: 是否跳过第一个消息段（默认为True）
    """
    segs = event.get_messages()
    segs = segs[1:] if skip_first_seg else segs
    ats = {str(seg.qq) for seg in segs if isinstance(seg, At)}
    ats.update(
        arg[1:]
        for arg in event.message_str.split()
        if arg.startswith("@") and arg[1:].isdigit()
    )
    if noself:
        ats.discard(event.get_self_id())
    if block_ids:
        ats.difference_update(block_ids)
    return list(ats)


def parse_multi_input(raw: str, total: int) -> tuple[set[int], set[str]]:
    """
    解析文本参数，支持：
    - 空格分隔
    - 序号
    - 区间（1~5 / 1-5）
    - 直接 ID（QQ / 群号）

    返回：
        indexes: 0-based 索引集合
        ids:     明确 ID 集合
    """
    indexes: set[int] = set()
    ids: set[str] = set()

    if not raw:
        return indexes, ids

    for token in raw.strip().split():
        token = token.strip()
        if not token:
            continue

        # 区间
        m = re.fullmatch(r"(\d+)\s*[~-]\s*(\d+)", token)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                if 1 <= i <= total:
                    indexes.add(i - 1)
            continue

        # 单数字
        if token.isdigit():
            num = int(token)
            if 1 <= num <= total:
                indexes.add(num - 1)
            else:
                ids.add(token)

    return indexes, ids
