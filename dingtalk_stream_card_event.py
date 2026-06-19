import time

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent


class DingtalkStreamCardMessageEvent(DingtalkMessageEvent):
    async def send(self, message: MessageChain) -> None:
        logger.debug(
            "钉钉流式卡片：进入普通 send，send_normal_reply_as_card=%s, plain_length=%s",
            getattr(self.adapter, "send_normal_reply_as_card", False),
            len("".join(segment.text for segment in message.chain if isinstance(segment, Plain))),
        )
        if not getattr(self.adapter, "send_normal_reply_as_card", False):
            return await super().send(message)

        logger.info("钉钉流式卡片：检测到普通回复，尝试按卡片发送")
        if not self.adapter or not getattr(self.adapter, "enable_stream_card", False):
            logger.debug("钉钉流式卡片：普通回复卡片发送未启用，改用普通消息")
            return await super().send(message)

        if not getattr(self.adapter, "card_template_id", ""):
            logger.warning("钉钉流式卡片：card_template_id 为空，普通回复改用普通消息")
            return await super().send(message)

        incoming_message = getattr(self.message_obj, "raw_message", None)
        if incoming_message is None:
            logger.warning("钉钉流式卡片：缺少原始 incoming message，普通回复改用普通消息")
            return await super().send(message)

        text = "".join(
            segment.text for segment in message.chain if isinstance(segment, Plain)
        )
        non_plain_chain = MessageChain(
            chain=[
                segment
                for segment in message.chain
                if not isinstance(segment, Plain)
            ],
        )

        if not text:
            logger.info("钉钉流式卡片：普通回复没有纯文本内容，改用普通消息")
            return await super().send(message)

        card_token = await self.adapter.create_message_card(
            message_id=getattr(self.message_obj, "message_id", ""),
            incoming_message=incoming_message,
        )
        if not card_token:
            logger.warning("钉钉流式卡片：普通回复卡片创建失败，改用普通消息")
            return await super().send(message)

        await self.adapter.send_card_message(
            card_token=card_token,
            content=text,
            is_final=True,
        )

        if non_plain_chain.chain:
            await super().send(non_plain_chain)

    async def _send_streaming_as_plain_text(self, generator) -> None:
        buffer = None
        async for chain in generator:
            if buffer is None:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)

        if buffer is None:
            return

        buffer.squash_plain()
        await self.send(buffer)

    async def send_streaming(self, generator, use_fallback: bool = False):
        logger.debug("钉钉流式卡片：进入 send_streaming")
        if not self.adapter:
            logger.error("钉钉流式卡片失败：缺少 adapter")
            return await self._send_streaming_as_plain_text(generator)

        if not getattr(self.adapter, "enable_stream_card", False):
            logger.info("钉钉流式卡片：enable_stream_card 未开启，回退为普通文本消息")
            return await self._send_streaming_as_plain_text(generator)

        if not getattr(self.adapter, "card_template_id", ""):
            logger.warning(
                "已启用钉钉流式卡片，但 card_template_id 为空，回退为普通文本消息",
            )
            return await self._send_streaming_as_plain_text(generator)

        incoming_message = getattr(self.message_obj, "raw_message", None)
        if incoming_message is None:
            logger.warning(
                "钉钉流式卡片失败：缺少原始 incoming message，回退为普通文本消息",
            )
            return await self._send_streaming_as_plain_text(generator)

        card_token = await self.adapter.create_message_card(
            message_id=getattr(self.message_obj, "message_id", ""),
            incoming_message=incoming_message,
        )
        if not card_token:
            logger.warning("钉钉流式卡片：卡片创建失败，回退为普通文本消息")
            return await self._send_streaming_as_plain_text(generator)

        logger.info("钉钉流式卡片：卡片创建成功，开始流式更新")
        full_content = ""
        pending_chain = MessageChain()
        last_update_at = 0.0
        update_interval = max(
            0.1,
            float(getattr(self.adapter, "card_update_interval", 0.35) or 0.35),
        )

        async for chain in generator:
            for segment in chain.chain:
                if isinstance(segment, Plain):
                    full_content += segment.text
                else:
                    pending_chain.chain.append(segment)

            now = time.monotonic()
            if full_content and now - last_update_at >= update_interval:
                await self.adapter.send_card_message(
                    card_token=card_token,
                    content=full_content,
                    is_final=False,
                )
                last_update_at = now

        await self.adapter.send_card_message(
            card_token=card_token,
            content=full_content,
            is_final=True,
        )
        logger.info("钉钉流式卡片：流式更新完成")

        if pending_chain.chain:
            await self.send(pending_chain)

        return None
