from astrbot.api.star import Context, Star


class DingtalkStreamCardPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        from . import dingtalk_stream_card_adapter  # noqa: F401
