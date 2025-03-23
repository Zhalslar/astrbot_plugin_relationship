
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

@register("人际关系查看器", "Zhalslar", "查看QQ加的所有好友、群聊的信息", "1.0.0", "https://github.com/Zhalslar/astrbot_plugin_relationship")
class Relationship(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("群列表")
    async def show_groups_info(self, event: AstrMessageEvent):
        """查看加入的所有群聊信息"""
        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        group_list =  await client.api.call_action('get_group_list')
        group_info = "\n".join(f"{g['group_id']}: {g['group_name']}" for g in group_list)
        yield event.plain_result(f"【群列表】共加入{len(group_list)}个群：\n{group_info}")

    @filter.command("好友列表")
    async def show_friends_info(self, event: AstrMessageEvent):
        """查看所有好友信息"""
        assert isinstance(event, AiocqhttpMessageEvent)
        client = event.bot
        friend_list = await client.api.call_action('bot.get_friend_list')
        friend_info = "\n".join(f"{f['user_id']}: {f['nickname']}" for f in friend_list)
        yield event.plain_result(f"【好友列表】共{len(friend_list)}位好友：\n{friend_info}")




