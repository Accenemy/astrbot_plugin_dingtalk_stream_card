import asyncio
from typing import Any, cast

import dingtalk_stream

from astrbot import logger
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DingtalkPlatformAdapter,
)
from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent
from astrbot.core.platform.register import register_platform_adapter

from .dingtalk_stream_card_event import DingtalkStreamCardMessageEvent


DEFAULT_CONFIG = {
    "id": "dingtalk_stream_card",
    "type": "dingtalk_stream_card",
    "enable": False,
    "client_id": "",
    "client_secret": "",
    "enable_stream_card": True,
    "card_template_id": "",
    "card_content_key": "content",
    "card_update_interval": 0.35,
    "send_normal_reply_as_card": False,
}


CONFIG_METADATA = {
    "client_id": {
        "description": "Client ID / AppKey",
        "type": "string",
        "hint": "钉钉机器人的 Client ID 或 AppKey。",
    },
    "client_secret": {
        "description": "Client Secret / AppSecret",
        "type": "string",
        "hint": "钉钉机器人的 Client Secret 或 AppSecret。",
        "obscure": True,
    },
    "enable_stream_card": {
        "description": "启用流式卡片",
        "type": "bool",
        "hint": "开启后，LLM 流式回复会通过钉钉互动 AI 卡片逐步更新。关闭后，仍使用普通钉钉消息回复。",
    },
    "card_template_id": {
        "description": "卡片模板 ID",
        "type": "string",
        "hint": "钉钉互动卡片模板 ID。启用流式卡片时必填。",
    },
    "card_content_key": {
        "description": "卡片内容变量名",
        "type": "string",
        "hint": "钉钉卡片模板中用于接收流式文本/Markdown 内容的变量名。默认：content。",
    },
    "card_update_interval": {
        "description": "卡片更新间隔",
        "type": "float",
        "hint": "两次卡片更新之间的最小间隔，单位秒。默认：0.35。",
    },
    "send_normal_reply_as_card": {
        "description": "普通回复也使用卡片",
        "type": "bool",
        "hint": "用于诊断卡片模板是否可用。开启后，即使 AstrBot 没有走流式回复，也会尝试把纯文本回复作为钉钉卡片发送。",
    },
}


@register_platform_adapter(
    "dingtalk_stream_card",
    "支持互动 AI 卡片流式回复的钉钉适配器",
    default_config_tmpl=DEFAULT_CONFIG,
    adapter_display_name="钉钉流式卡片",
    support_streaming_message=True,
    config_metadata=CONFIG_METADATA,
)
class DingtalkStreamCardPlatformAdapter(DingtalkPlatformAdapter):
    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, platform_settings, event_queue)
        self.enable_stream_card = _to_bool(
            platform_config.get("enable_stream_card", True),
        )
        self.card_template_id = str(platform_config.get("card_template_id", "") or "")
        self.card_content_key = str(
            platform_config.get("card_content_key", "content") or "content",
        )
        self.card_update_interval = _to_float(
            platform_config.get("card_update_interval", 0.35),
            0.35,
        )
        self.send_normal_reply_as_card = _to_bool(
            platform_config.get("send_normal_reply_as_card", False),
        )
        self._card_sessions: dict[str, tuple[Any, str]] = {}
        logger.info(
            "钉钉流式卡片适配器已初始化：enable_stream_card=%s, card_template_id=%s, card_content_key=%s, card_update_interval=%s, send_normal_reply_as_card=%s",
            self.enable_stream_card,
            "已填写" if self.card_template_id else "未填写",
            self.card_content_key,
            self.card_update_interval,
            self.send_normal_reply_as_card,
        )

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="dingtalk_stream_card",
            description="支持互动 AI 卡片流式回复的钉钉适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=True,
            support_proactive_message=True,
        )

    def create_event(self, message: AstrBotMessage) -> DingtalkMessageEvent:
        logger.debug(
            "钉钉流式卡片：创建插件事件类 DingtalkStreamCardMessageEvent，message_id=%s",
            getattr(message, "message_id", ""),
        )
        return DingtalkStreamCardMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client,
            adapter=self,
        )

    async def handle_msg(self, abm: AstrBotMessage) -> None:
        logger.debug(
            "钉钉流式卡片：提交插件事件，platform_id=%s, message_id=%s",
            self.meta().id,
            getattr(abm, "message_id", ""),
        )
        self.commit_event(self.create_event(abm))

    async def create_message_card(
        self,
        message_id: str,
        incoming_message: dingtalk_stream.ChatbotMessage,
    ) -> str:
        logger.info(
            "钉钉流式卡片：准备创建卡片，message_id=%s, template=%s, content_key=%s",
            message_id or "空",
            "已填写" if self.card_template_id else "未填写",
            self.card_content_key,
        )
        try:
            card_replier = dingtalk_stream.AICardReplier(
                self.client_,
                incoming_message,
            )
            card_instance_id = await card_replier.async_create_and_deliver_card(
                self.card_template_id,
                {self.card_content_key: ""},
            )
        except AttributeError as e:
            logger.error(
                "钉钉流式卡片失败：当前 dingtalk_stream 包没有 AICardReplier：%s",
                e,
            )
            return ""
        except Exception as e:
            logger.error("钉钉流式卡片创建失败：%s", e)
            return ""

        if not card_instance_id:
            logger.error("钉钉流式卡片创建失败：card_instance_id 为空")
            return ""

        logger.info("钉钉流式卡片：卡片创建成功，card_instance_id=%s", card_instance_id)
        card_token = message_id or card_instance_id
        self._card_sessions[card_token] = (card_replier, card_instance_id)
        return card_token

    async def send_card_message(
        self,
        card_token: str,
        content: str,
        is_final: bool,
    ) -> None:
        session = self._card_sessions.get(card_token)
        if not session:
            logger.warning("钉钉流式卡片更新已跳过：找不到卡片会话")
            return

        card_replier, card_instance_id = session
        try:
            logger.debug(
                "钉钉流式卡片：更新卡片，final=%s, content_length=%s",
                is_final,
                len(content),
            )
            await card_replier.async_streaming(
                card_instance_id,
                content_key=self.card_content_key,
                content_value=content,
                append=False,
                finished=is_final,
                failed=False,
            )
        except Exception as e:
            logger.error("钉钉流式卡片更新失败：%s", e)
            if is_final:
                self._card_sessions.pop(card_token, None)
            return

        if is_final:
            self._card_sessions.pop(card_token, None)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
