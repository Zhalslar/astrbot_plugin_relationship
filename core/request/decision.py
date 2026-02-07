from dataclasses import dataclass
from aiocqhttp import CQHttp

from ..config import PluginConfig
from .model import FriendRequest, GroupRequest, BaseRequest


@dataclass
class RequestResult:
    admin_reply: str = ""
    user_reply: str = ""
    event_reply: str = ""
    approve: bool | None = None
    block_group: bool | None = None
    block_user: bool | None = None


class RequestDecision:
    """请求决策层"""

    def __init__(
        self,
        client: CQHttp,
        request: BaseRequest,
        config: PluginConfig,
    ):
        self.client = client
        self.req = request
        self.cfg = config

    async def decide(
        self,
        approve: bool | None = None,
        extra: str = "",
    ) -> RequestResult:
        result = RequestResult(approve=approve)
        result.admin_reply = self.req.to_display_text()

        # 自动规则（最高优先级）
        if approve is None:
            if self._auto_decide(result):
                return result

        # aidian_verify
        afdian_approved = self._check_afdian()

        # 自动决策
        if approve is None:
            if isinstance(self.req, FriendRequest):
                self._decide_friend(afdian_approved, result)
            elif isinstance(self.req, GroupRequest):
                self._decide_group(self.req, afdian_approved, result)

        # 指令决策
        else:
            if isinstance(self.req, FriendRequest):
                await self._decide_friend_cmd(self.req, approve, result, extra)
            elif isinstance(self.req, GroupRequest):
                await self._decide_group_cmd(self.req, approve, result, extra)

        return result

    # ======================================================
    # 自动决策（由配置驱动）
    # ======================================================
    def _auto_decide(self, result: RequestResult) -> bool:
        cfg = self.cfg.request

        # ---------- 好友请求 ----------
        if isinstance(self.req, FriendRequest):
            uid = str(self.req.user_id)

            # 1. 全局自动拒绝
            if cfg.auto_reject_friend:
                result.approve = False
                result.user_reply = "已自动拒绝好友请求"
                result.admin_reply += "\n自动处理：已自动拒绝"
                return True

            # 2. 用户黑名单
            if uid in cfg.user_blacklist:
                result.approve = False
                result.user_reply = "你已被加入黑名单，无法添加好友"
                result.block_user = True
                result.admin_reply += "\n自动处理：该用户在黑名单中"
                return True

            # 3. 自动同意
            if cfg.auto_agree_friend:
                result.approve = True
                result.user_reply = "已自动同意好友请求"
                result.admin_reply += "\n自动处理：已自动同意"
                return True

        # ---------- 群邀请 ----------
        if isinstance(self.req, GroupRequest):
            gid = str(self.req.group_id)

            # 1. 全局自动拒绝
            if cfg.auto_reject_group:
                result.approve = False
                result.user_reply = "已自动拒绝群邀请"
                result.admin_reply += "\n自动处理：已自动拒绝"
                return True

            # 2. 群黑名单
            if gid in cfg.group_blacklist:
                result.approve = False
                result.user_reply = "该群已被列入黑名单，自动拒绝"
                result.block_group = True
                result.admin_reply += "\n自动处理：该群在黑名单中"
                return True

            # 3. 自动同意
            if cfg.auto_agree_group:
                result.approve = True
                result.user_reply = "已自动同意群邀请"
                result.admin_reply += "\n自动处理：已自动同意"
                return True

        return False

    # ======================================================
    # Afdian 校验
    # ======================================================
    def _check_afdian(self) -> bool:
        try:
            from ...afdian import afdian_verify

            return afdian_verify(remark=str(self.req.requester_id))
        except ImportError:
            return False

    # ======================================================
    # 原有业务逻辑（未自动处理时）
    # ======================================================
    def _decide_friend(self, afdian_ok: bool, result: RequestResult):
        if afdian_ok:
            result.approve = True
            result.admin_reply += "\nAfdian_verify: approved!"
        else:
            result.user_reply = "好友申请已收到，正在审核中，请耐心等待"

    def _decide_group(
        self,
        req: GroupRequest,
        afdian_ok: bool,
        result: RequestResult,
    ):
        if afdian_ok:
            result.approve = True
            result.admin_reply += "\nAfdian_verify: approved!"
            return

        if self.cfg.manage_group:
            result.user_reply = (
                f"群邀请已收到，需要在审核群 {self.cfg.manage_group} 审批后才能加入"
            )
        else:
            result.user_reply = "群邀请已收到，需要审核通过后才能加入"

        if self.cfg.is_black_group(req.group_id):
            result.admin_reply += "\n警告: 该群为黑名单群聊，请谨慎通过"
            result.user_reply += "\n该群已被列入黑名单，可能不会通过审核"

    # ======================================================
    # 指令处理（管理员）
    # ======================================================
    async def _decide_friend_cmd(
        self,
        req: FriendRequest,
        approve: bool,
        result: RequestResult,
        extra: str = "",
    ):
        friend_list = await self.client.get_friend_list()
        uids = {str(f["user_id"]) for f in friend_list}

        if req.user_id in uids:
            result.event_reply = f"【{req.nickname}】已经是我的好友啦"
            result.approve = None
            return

        if approve:
            result.approve = True
            result.event_reply = f"已同意好友：{req.nickname}"
            if extra:
                result.event_reply += f"\n备注：{extra}"
        else:
            result.approve = False
            result.event_reply = f"已拒绝好友：{req.nickname}"
            if extra:
                result.event_reply += f"\n理由：{extra}"

    async def _decide_group_cmd(
        self,
        req: GroupRequest,
        approve: bool,
        result: RequestResult,
        extra: str = "",
    ):
        group_list = await self.client.get_group_list()
        gids = {str(g["group_id"]) for g in group_list}

        if str(req.group_id) in gids:
            result.event_reply = f"我已经在【{req.group_name}】里啦"
            result.approve = None
            return

        if approve:
            result.approve = True
            result.block_group = False
            result.event_reply = f"已同意群邀请：{req.group_name}"
        else:
            result.approve = False
            result.event_reply = f"已拒绝群邀请：{req.group_name}"
            if extra:
                result.event_reply += f"\n理由：{extra}"
