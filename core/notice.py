from aiocqhttp import CQHttp

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig

from .utils import convert_duration_advanced, get_nickname


class NoticeHandler:
    """处理群聊相关事件（如管理员变动、禁言、踢出、邀请等）"""

    # 回复模板字典
    REPLY_TEMPLATES = {
        # 管理员变动
        "admin_set": {
            "admin": "哇！我成为了 {group_name}({group_id}) 的管理员",
            "operator": "芜湖~拿到管理了",
        },
        "admin_unset": {
            "admin": "呜呜ww.. 我在 {group_name}({group_id}) 的管理员被撤了",
            "operator": "呜呜ww..干嘛撤掉我管理",
        },
        # 禁言事件
        "ban_lift": {
            "admin": "好耶！{operator_name} 在 {group_name}({group_id}) 解除了我的禁言",
            "operator": "感谢解禁",
        },
        "ban_set": {
            "admin": "呜呜ww..我在 {group_name}({group_id}) 被 {operator_name} 禁言了{duration_str}",
        },
        "ban_exceed": {
            "suffix": "\n禁言时间超过{max_duration_str}，我退群了",
        },
        # 被踢事件
        "kicked": {
            "admin": "呜呜ww..我被 {operator_name} 踢出了 {group_name}({group_id})，已将此群拉进黑名单",
        },
        # 被邀请事件
        "invited": {
            "admin": "主人..我被 {operator_name} 拉进了 {group_name}({group_id})。",
        },
        "invited_blacklist": {
            "suffix": "\n群聊 {group_name}({group_id}) 在黑名单里，我退群了",
            "operator": "把我踢了还想要我回来？退了退了",
        },
        "invited_capacity_exceeded": {
            "suffix": "\n我已经加了{group_count}个群（超过了{max_capacity}个），这群我退了",
            "operator": "我最多只能加{max_capacity}个群，现在已经加了{group_count}个群，请不要拉我进群了",
        },
        "invited_mutual_blacklist": {
            "suffix": "\n检测到群内存在互斥成员 {member_name}({member_id})，这群我退了",
            "operator": "我不想和{member_name}({member_id})在同一个群里，退了",
        },
    }

    def __init__(self, client: CQHttp, raw_message: dict, config: AstrBotConfig):
        self.client = client
        self.raw_message = raw_message
        self.config = config

        # 初始化结果状态
        self.admin_reply = ""
        self.operator_reply = ""
        self.delay_check = False
        self.leave_group = False

        # 提取基本信息
        self.user_id = str(raw_message.get("user_id", ""))
        self.group_id = str(raw_message.get("group_id", ""))
        self.operator_id = raw_message.get("operator_id", 0)
        self.notice_type = raw_message.get("notice_type", "")
        self.sub_type = raw_message.get("sub_type", "")

        # 延迟加载的信息
        self._group_name: str | None = None
        self._operator_name: str | None = None

    async def handle(self) -> tuple[str, str, bool, bool]:
        """处理通知事件的主入口"""
        match (self.notice_type, self.sub_type):
            case ("group_admin", _):
                await self._handle_admin_change()
            case ("group_ban", _):
                await self._handle_ban()
            case ("group_decrease", "kick_me"):
                await self._handle_kicked()
            case ("group_increase", "invite"):
                await self._handle_invited()

        return self.admin_reply, self.operator_reply, self.delay_check, self.leave_group

    async def _get_group_name(self) -> str:
        """获取群名称（懒加载）"""
        if self._group_name is None:
            group_info = await self.client.get_group_info(group_id=int(self.group_id))
            self._group_name = group_info.get("group_name", "")
        return self._group_name

    async def _get_operator_name(self) -> str:
        """获取操作者昵称（懒加载）"""
        if self._operator_name is None:
            self._operator_name = await get_nickname(
                self.client, user_id=self.operator_id, group_id=self.group_id
            )
        return self._operator_name

    def _format_reply(
        self, template_key: str, reply_type: str = "admin", **kwargs
    ) -> str:
        """格式化回复模板"""
        template = self.REPLY_TEMPLATES.get(template_key, {}).get(reply_type, "")
        return template.format(**kwargs) if template else ""

    def _format_suffix(self, template_key: str, **kwargs) -> str:
        """格式化后缀模板"""
        template = self.REPLY_TEMPLATES.get(template_key, {}).get("suffix", "")
        return template.format(**kwargs) if template else ""

    async def _handle_admin_change(self) -> None:
        """处理群管理员变动事件"""
        group_name = await self._get_group_name()
        context = {"group_name": group_name, "group_id": self.group_id}

        if self.sub_type == "set":
            self.admin_reply = self._format_reply("admin_set", "admin", **context)
            self.operator_reply = self._format_reply("admin_set", "operator")
        else:
            self.admin_reply = self._format_reply("admin_unset", "admin", **context)
            self.operator_reply = self._format_reply("admin_unset", "operator")

    async def _handle_ban(self) -> None:
        """处理群禁言事件"""
        duration = self.raw_message.get("duration", 0)
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        context = {
            "group_name": group_name,
            "group_id": self.group_id,
            "operator_name": operator_name,
        }

        if duration == 0:
            self.admin_reply = self._format_reply("ban_lift", "admin", **context)
            self.operator_reply = self._format_reply("ban_lift", "operator")
        else:
            duration_str = convert_duration_advanced(duration)
            self.admin_reply = self._format_reply(
                "ban_set", "admin", duration_str=duration_str, **context
            )

            if duration > self.config["max_ban_duration"]:
                max_duration_str = convert_duration_advanced(
                    self.config["max_ban_duration"]
                )
                self.admin_reply += self._format_suffix(
                    "ban_exceed", max_duration_str=max_duration_str
                )
                self.leave_group = True

    async def _handle_kicked(self) -> None:
        """处理被踢出群事件"""
        if self.group_id not in self.config["group_blacklist"]:
            self.config["group_blacklist"].append(self.group_id)
            self.config.save_config()

        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        self.admin_reply = self._format_reply(
            "kicked",
            "admin",
            operator_name=operator_name,
            group_name=group_name,
            group_id=self.group_id,
        )
        logger.info(f"群聊 {self.group_id} 已因被踢被加入黑名单。")

    async def _handle_invited(self) -> None:
        """处理被邀请进群事件"""
        group_name = await self._get_group_name()
        operator_name = await self._get_operator_name()

        context = {
            "group_name": group_name,
            "group_id": self.group_id,
            "operator_name": operator_name,
        }

        self.admin_reply = self._format_reply("invited", "admin", **context)

        # 执行各项检查
        if await self._check_group_blacklist(context):
            return
        if await self._check_group_capacity(context):
            return
        if await self._check_mutual_blacklist(context):
            return

        # 所有检查通过，进行延时抽查
        self.delay_check = True

    async def _check_group_blacklist(self, context: dict) -> bool:
        """检查群是否在黑名单中"""
        if self.group_id in self.config["group_blacklist"]:
            self.admin_reply += self._format_suffix("invited_blacklist", **context)
            self.operator_reply = self._format_reply("invited_blacklist", "operator")
            self.leave_group = True
            return True
        return False

    async def _check_group_capacity(self, context: dict) -> bool:
        """检查群数量是否超过最大容量"""
        group_list = await self.client.get_group_list()
        max_capacity = self.config["max_group_capacity"]

        if len(group_list) > max_capacity:
            self.admin_reply += self._format_suffix(
                "invited_capacity_exceeded",
                group_count=len(group_list),
                max_capacity=max_capacity,
                **context,
            )
            self.operator_reply = self._format_reply(
                "invited_capacity_exceeded",
                "operator",
                group_count=len(group_list),
                max_capacity=max_capacity,
            )
            self.leave_group = True
            return True
        return False

    async def _check_mutual_blacklist(self, context: dict) -> bool:
        """检查群内是否存在互斥成员"""
        mutual_blacklist_set = set(self.config["mutual_blacklist"]).copy()
        mutual_blacklist_set.discard(self.user_id)

        member_list = await self.client.get_group_member_list(
            group_id=int(self.group_id)
        )
        member_ids = [str(member["user_id"]) for member in member_list]
        common_ids = set(member_ids) & mutual_blacklist_set

        if common_ids:
            member_id = common_ids.pop()
            member_name = await get_nickname(
                self.client, user_id=int(member_id), group_id=self.group_id
            )

            self.admin_reply += self._format_suffix(
                "invited_mutual_blacklist",
                member_name=member_name,
                member_id=member_id,
                **context,
            )
            self.operator_reply = self._format_reply(
                "invited_mutual_blacklist",
                "operator",
                member_name=member_name,
                member_id=member_id,
            )
            self.leave_group = True
            return True
        return False



