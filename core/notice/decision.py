from dataclasses import dataclass
from aiocqhttp import CQHttp
from ..config import PluginConfig
from ..utils import convert_duration_advanced, get_nickname
from .model import NoticeMessage


@dataclass
class NoticeResult:
    """业务结果对象"""

    admin_reply: str = ""
    operator_reply: str = ""

    check_group: bool = False
    leave_group: bool = False
    black_group: bool = False
    black_user: bool = False


class NoticeDecision:
    """通知决策层"""

    def __init__(
        self,
        client: CQHttp,
        message: NoticeMessage,
        config: PluginConfig,
    ):
        self.cfg = config
        self.ncfg = config.notice
        self.client = client
        self.msg = message

        self._group_name: str | None = None
        self._operator_name: str | None = None

    # ---------
    # 公共入口
    # ---------
    async def decide(self) -> NoticeResult:
        result = NoticeResult()

        match (self.msg.notice_type, self.msg.sub_type):
            case ("group_admin", _):
                await self._handle_admin_change(result)
            case ("group_ban", _):
                await self._handle_ban(result)
            case ("group_decrease", "kick_me"):
                await self._handle_kicked(result)
            case ("group_increase", "invite"):
                await self._handle_invited(result)

        return result

    # ----------------
    # 基础信息获取
    # ----------------
    async def _get_group_name(self) -> str:
        if self._group_name is None:
            info = await self.client.get_group_info(group_id=int(self.msg.group_id))
            self._group_name = info.get("group_name", "")
        return self._group_name

    async def _get_operator_name(self) -> str:
        if self._operator_name is None:
            self._operator_name = await get_nickname(
                self.client,
                user_id=int(self.msg.operator_id),
                group_id=self.msg.group_id,
            )
        return self._operator_name

    # ----------------
    # 各事件处理
    # ----------------
    async def _handle_admin_change(self, result: NoticeResult):
        group_name = await self._get_group_name()
        gid = self.msg.group_id

        if self.msg.sub_type == "set":
            result.admin_reply = f"哇！我成为了 {group_name}({gid}) 的管理员"
            result.operator_reply = "芜湖~拿到管理了"
        else:
            result.admin_reply = f"呜呜ww.. 我在 {group_name}({gid}) 的管理员被撤了"
            result.operator_reply = "呜呜ww..干嘛撤掉我管理"

    async def _handle_ban(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()
        gid = self.msg.group_id

        if self.msg.duration == 0:
            result.admin_reply = (
                f"好耶！{operator_name} 在 {group_name}({gid}) 解除了我的禁言"
            )
            result.operator_reply = "感谢解禁"
            return

        duration_str = convert_duration_advanced(self.msg.duration)
        result.admin_reply = (
            f"呜呜ww..我在 {group_name}({gid}) 被 {operator_name} 禁言了{duration_str}"
        )

        if self.msg.duration > self.ncfg.max_duration:
            max_str = convert_duration_advanced(self.ncfg.max_duration)
            result.admin_reply += f"\n禁言时间超过{max_str}，我退群了"
            result.leave_group = True

    async def _handle_kicked(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()
        gid = self.msg.group_id 
        result.admin_reply = f"呜呜ww..我被 {operator_name} 踢出了 {group_name}({gid})"
        if self.cfg.notice.kick_block_group:
            result.black_group = True
            result.admin_reply += "，已将此群拉进黑名单"

        if self.cfg.notice.kick_block_user:
            result.black_user = True
            result.admin_reply += "，已将此人拉进黑名单"


    async def _handle_invited(self, result: NoticeResult):
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()
        gid = int(self.msg.group_id)

        result.admin_reply = f"主人..我被 {operator_name} 拉进了 {group_name}({gid})。"

        # 审批员拉群直接放行，其余人按规则过滤
        if self.msg.operator_id not in self.cfg.manage_users:
            if await self._check_blacklist(result, group_name, gid):
                return
            if await self._check_group_size(result, gid):
                return
            if await self._check_capacity(result):
                return
            if await self._check_mutual_blacklist(result, gid):
                return

        # 走到这里说明要么审批员拉群，要么全部检查通过
        result.check_group = True

    # ----------------
    # 各种检查
    # ----------------
    async def _check_blacklist(
        self, result: NoticeResult, group_name: str, gid: int
    ) -> bool:
        if self.cfg.is_black_group(self.msg.group_id):
            result.admin_reply += f"\n群聊 {group_name}({gid}) 在黑名单里，我退群了"
            result.operator_reply = "把我踢了还想要我回来？退了退了"
            result.leave_group = True
            return True
        return False

    async def _check_capacity(self, result: NoticeResult) -> bool:
        group_list = await self.client.get_group_list()
        max_cap = self.ncfg.max_group_capacity

        if len(group_list) > max_cap:
            result.admin_reply += (
                f"\n我已经加了{len(group_list)}个群（超过了{max_cap}个），这群我退了"
            )
            result.operator_reply = f"我最多只能加{max_cap}个群，现在已经加了{len(group_list)}个群，请不要拉我进群了"
            result.leave_group = True
            return True
        return False

    async def _check_mutual_blacklist(self, result: NoticeResult, gid: int) -> bool:
        mutual = set(self.ncfg.mutual_blacklist)
        mutual.discard(self.msg.user_id)

        members = await self.client.get_group_member_list(group_id=int(gid))
        member_ids = {str(m["user_id"]) for m in members}

        common = member_ids & mutual
        if not common:
            return False

        member_id = common.pop()
        member_name = await get_nickname(
            self.client,
            user_id=int(member_id),
            group_id=gid,
        )

        result.admin_reply += (
            f"\n检测到群内存在互斥成员 {member_name}({member_id})，这群我退了"
        )
        result.operator_reply = f"我不想和{member_name}({member_id})在同一个群里，退了"
        result.leave_group = True
        return True

    async def _check_group_size(self, result: NoticeResult, gid: int) -> bool:
        """
        返回 True 表示已触发退群，不再继续后续检查
        """
        group_info = await self.client.get_group_info(group_id=int(gid), no_cache=True)
        member_count = group_info.get("member_count", 0)

        # 1. 小群限制
        min_size = self.ncfg.min_group_size
        if self.ncfg.block_small_group and member_count <= min_size:
            result.admin_reply += f"\n群人数 {member_count} ≤ {min_size}，小群我退了"
            result.operator_reply = f"小群不加，人数 {member_count} ≤ {min_size}"
            result.leave_group = True
            return True

        # 2. 大群限制
        max_size = self.ncfg.max_group_size
        if max_size and member_count > max_size:
            result.admin_reply += f"\n群人数 {member_count} > {max_size}，大群我退了"
            result.operator_reply = f"大群不加，人数 {member_count} > {max_size}"
            result.leave_group = True
            return True

        return False
