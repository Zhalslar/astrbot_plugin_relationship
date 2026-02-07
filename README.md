<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_relationship?name=astrbot_plugin_relationship&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_relationship

_✨ 人际关系管理器 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

> 注意：**好友列表** 与 **群列表** 为纯文本输出，如需转图片请使用输出增强类插件（例如 [astrbot_plugin_outputpro](https://github.com/Zhalslar/astrbot_plugin_outputpro)）。

## 简介

为 AstrBot 提供的关系管理插件，支持好友/群列表查看、好友与群邀请审核、自动处理规则、踢出与禁言通知、黑名单维护，以及聊天记录抽查等能力，方便集中管理 bot 的人际关系与群管理风险。

## 功能一览

- 好友列表与群列表查询（纯文本）。
- 批量退群、批量删好友（支持序号、ID、区间、@）。
- 好友申请与群邀请：自动审核规则（黑名单/自动同意/自动拒绝）与手动审核（引用申请消息后用 `同意/拒绝`）。
- 群事件通知处理：管理员变动、禁言、被踢、被邀请入群。
- 风险控制：小群/超大群自动退群、超过最大群容量自动退群、被踢出后自动拉黑群/用户、互斥成员（`mutual_blacklist`）检测。
- 聊天记录抽查与新群自动抽查（可延迟）。

## 安装

- 在 AstrBot 插件市场搜索 `astrbot_plugin_relationship` 一键安装。
- 或手动克隆到插件目录：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/Zhalslar/astrbot_plugin_relationship
```

## 配置

在 AstrBot 面板中配置：`插件管理 -> astrbot_plugin_relationship -> 操作 -> 插件配置`。

## 指令

| 指令 | 说明 | 权限 |
|:--|:--|:--|
| `群列表` | 查看 bot 加入的所有群 | 管理员 |
| `好友列表` | 查看 bot 的所有好友 | 管理员 |
| `退群 <序号/群号/区间>` | 退群，支持批量与区间 | 管理员 |
| `删好友 <@QQ/序号/区间>` | 删除好友，支持批量与区间 | 管理员 |
| `加审核员 @某人` | 添加审核员 | 建议限制为管理员 |
| `减审核员 @某人` | 移除审核员 | 建议限制为管理员 |
| `同意 [备注]` | 同意好友/群邀请 | 仅审核员 |
| `拒绝 [理由]` | 拒绝好友/群邀请 | 仅审核员 |
| `抽查 [群号/@群友/QQ] [数量]` | 抽查聊天记录 | 管理员 |

使用说明：

- `同意/拒绝` 必须**引用申请消息**使用。
- `退群/删好友` 支持空格分隔、区间（`1-5` / `1~5`）与批量输入。
- `抽查` 若未指定目标，会随机抽查一个群。

## 机制说明

**申请/邀请事件**：先走自动规则（黑名单/自动同意/自动拒绝），若未自动处理，将通知审核群或管理员，等待手动 `同意/拒绝`。

**群事件通知**：管理员变动、禁言、被踢、被邀请入群会通知审核群/管理员，可根据配置自动退群、拉黑群/用户。

**新群自动抽查**：被邀请入群且通过规则校验后，会自动转发该群的近期消息到审核群或管理员。

## 示例图

![example](https://github.com/user-attachments/assets/656ee439-a215-4aae-8ddd-96fad9067e6a)

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 注意事项

- 如果未配置 `manage_group` 且无管理员 ID，将无法发送审核与通知消息。
- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
