# AstrBot 钉钉流式卡片插件

这个插件会注册一个新的 AstrBot 平台适配器：

```text
dingtalk_stream_card
```

它不会修改 AstrBot 内置的 `dingtalk` 适配器。关闭流式卡片开关、未配置钉钉卡片模板 ID，或卡片创建失败时，会自动回退为普通钉钉消息。

## 为什么做这个插件

近期 AstrBot 版本的内置钉钉配置里仍然能看到 `card_template_id`，但当前内置钉钉 `send_streaming()` 实际会把整段回复攒完，再作为普通消息发出。这个插件不改内置适配器，而是新增一个独立钉钉平台，只覆盖流式发送路径。

## 安装

### 通过 WebUI 安装

在 AstrBot WebUI 的插件管理中，使用 GitHub 仓库地址安装本插件。安装完成后，重启 AstrBot 或重新加载平台适配器。

### 手动安装

把整个插件目录复制到 AstrBot 的插件目录。

常见容器路径：

```bash
docker compose cp astrbot_plugin_dingtalk_stream_card astrbot:/AstrBot/data/plugins/astrbot_plugin_dingtalk_stream_card
docker compose restart astrbot
```

如果你的服务名不是 `astrbot`，先查看实际服务名：

```bash
docker compose ps
```

也可以上传插件 ZIP 包，但推荐以 GitHub 仓库方式安装，方便后续更新。

## 配置

在 AstrBot WebUI 新增平台，选择：

```text
钉钉流式卡片
```

使用和内置钉钉适配器相同的钉钉凭据：

```json
{
  "client_id": "your_app_key_or_client_id",
  "client_secret": "your_app_secret_or_client_secret",
  "enable_stream_card": true,
  "card_template_id": "your_dingtalk_card_template_id",
  "card_content_key": "content",
  "card_update_interval": 0.35,
  "send_normal_reply_as_card": false
}
```

钉钉卡片模板里必须有一个变量名和 `card_content_key` 对应。默认是：

```text
content
```

同时确认 AstrBot 的模型/provider 已开启流式输出。否则 AstrBot 本身不会产生增量 chunk，平台层也就无法逐步更新卡片。

建议禁用内置 `钉钉(DingTalk)` 平台实例，只保留 `钉钉流式卡片`，避免同一个钉钉机器人被两个平台适配器同时消费。

## 排查

如果收到的还是普通消息，优先看 AstrBot 日志里有没有：

```text
钉钉流式卡片：进入 send_streaming
```

没有这行，说明 AstrBot 没有走流式回复链路，通常是模型/provider 没开流式输出，或当前回复不是 LLM 流式结果。

有这行但仍是普通消息，继续看日志里的回退原因，例如 `card_template_id 为空`、`卡片创建失败`、`缺少原始 incoming message`。

可以临时开启：

```json
{
  "send_normal_reply_as_card": true
}
```

这个开关会把非流式的纯文本回复也尝试作为钉钉卡片发送，用来验证卡片模板和钉钉权限是否正常。

如果开启后日志里没有：

```text
钉钉流式卡片：进入普通 send
```

说明当前实际回复没有走 `钉钉流式卡片` 这个平台，通常是旧的内置钉钉平台还在启用，或者 WebUI 里当前平台实例没有切到本插件注册的平台。

如果能看到：

```text
钉钉流式卡片：提交插件事件
钉钉流式卡片：创建插件事件类 DingtalkStreamCardMessageEvent
```

说明平台入口已经正确使用插件事件类。

## 回退

禁用或删除 `钉钉流式卡片` 平台实例，再切回内置钉钉适配器即可。因为插件没有修改核心文件，所以回退只需要移除插件或平台配置。

## 许可

MIT
