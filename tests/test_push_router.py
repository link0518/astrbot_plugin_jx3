"""会话路由单测：路由捕获、按 self_id 定向发送与无路由回退。

验证核心诉求：多 QQ 账号共用同一 aiocqhttp 平台时，主动推送显式携带
``self_id``，不再依赖「恰好一条连接」的兜底。
"""

from types import SimpleNamespace

import pytest

from astrbot_plugin_jx3.core import push_router
from astrbot_plugin_jx3.core.push_router import PushRouter


class FakeBot:
    """aiocqhttp 风格：call_action 直接挂在 bot 上，记录每次调用。"""

    def __init__(self):
        self.calls = []

    async def call_action(self, action, **kwargs):
        self.calls.append((action, kwargs))


class FakeApiBot:
    """兼容形态：call_action 挂在 bot.api 上。"""

    def __init__(self, inner):
        self.api = inner


class FakeContext:
    """记录回退发送的 Context 替身。"""

    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message_chain):
        self.sent.append((session_id, message_chain))


class _FakeChain:
    """MessageChain 最小替身：支持 .message(text) 链式。"""

    def __init__(self):
        self.parts = []

    def message(self, text):
        self.parts.append(text)
        return self


@pytest.fixture()
def router():
    return PushRouter(FakeContext())


def _event(
    *,
    session="default:GroupMessage:903288678",
    bot=None,
    self_id="2377567195",
    group_id="903288678",
    sender="2497905156",
):
    return SimpleNamespace(
        unified_msg_origin=session,
        bot=bot,
        message_obj=SimpleNamespace(self_id=self_id),
        get_group_id=lambda: group_id,
        get_sender_id=lambda: sender,
    )


class TestRecord:
    def test_group_route_recorded(self, router):
        bot = FakeBot()
        router.record(_event(bot=bot))
        route = router._routes["default:GroupMessage:903288678"]
        assert route["bot"] is bot
        assert route["self_id"] == "2377567195"
        assert route["is_group"] is True
        assert route["target"] == 903288678

    def test_private_route_recorded(self, router):
        bot = FakeBot()
        router.record(
            _event(
                session="default:FriendMessage:2497905156",
                bot=bot,
                group_id="",
                sender="2497905156",
            )
        )
        route = router._routes["default:FriendMessage:2497905156"]
        assert route["is_group"] is False
        assert route["target"] == 2497905156

    def test_api_style_bot_supported(self, router):
        inner = FakeBot()
        router.record(_event(bot=FakeApiBot(inner)))
        assert router._routes["default:GroupMessage:903288678"]["bot"].api is inner

    def test_skips_when_fields_missing(self, router):
        bot = FakeBot()
        # 无会话
        router.record(_event(session="", bot=bot))
        # 无 bot
        router.record(_event(bot=None))
        # bot 无 call_action
        router.record(_event(bot=object()))
        # 无 self_id
        router.record(_event(bot=bot, self_id=None))
        # 目标非数字（无法用于 group_id/user_id）
        router.record(_event(bot=bot, group_id="abc", sender=""))
        assert router._routes == {}

    def test_latest_message_overwrites_route(self, router):
        bot_a, bot_b = FakeBot(), FakeBot()
        router.record(_event(bot=bot_a, self_id="111"))
        router.record(_event(bot=bot_b, self_id="222"))
        assert router._routes["default:GroupMessage:903288678"]["self_id"] == "222"


class TestSend:
    async def test_group_send_carries_self_id(self, router):
        bot = FakeBot()
        router.record(_event(bot=bot, self_id="2377567195"))
        await router.send("default:GroupMessage:903288678", "测试内容")
        action, kwargs = bot.calls[0]
        assert action == "send_group_msg"
        assert kwargs["group_id"] == 903288678
        assert kwargs["self_id"] == "2377567195"
        assert kwargs["message"] == [{"type": "text", "data": {"text": "测试内容"}}]
        # 路由命中时不走框架回退
        assert router.context.sent == []

    async def test_private_send_uses_user_id(self, router):
        bot = FakeBot()
        router.record(
            _event(
                session="default:FriendMessage:2497905156",
                bot=bot,
                group_id="",
                sender="2497905156",
            )
        )
        await router.send("default:FriendMessage:2497905156", "hi")
        action, kwargs = bot.calls[0]
        assert action == "send_private_msg"
        assert kwargs["user_id"] == 2497905156

    async def test_routed_send_error_propagates(self, router):
        class _FailBot(FakeBot):
            async def call_action(self, action, **kwargs):
                raise RuntimeError("账号已退群")

        router.record(_event(bot=_FailBot()))
        with pytest.raises(RuntimeError, match="账号已退群"):
            await router.send("default:GroupMessage:903288678", "x")
        # 失败不回退框架发送（避免掩盖真实原因）
        assert router.context.sent == []

    async def test_no_route_falls_back(self, router, monkeypatch):
        monkeypatch.setattr(push_router, "MessageChain", _FakeChain)
        await router.send("default:GroupMessage:1", "hello")
        assert router.context.sent == [("default:GroupMessage:1", router.context.sent[0][1])]
        assert router.context.sent[0][1].parts == ["hello"]

    async def test_stale_bot_drops_route_and_falls_back(self, router, monkeypatch):
        monkeypatch.setattr(push_router, "MessageChain", _FakeChain)
        session = "default:GroupMessage:903288678"
        router._routes[session] = {
            "bot": object(),  # 无 call_action，视为失效连接
            "self_id": "1",
            "is_group": True,
            "target": 903288678,
        }
        await router.send(session, "hi")
        assert session not in router._routes
        assert len(router.context.sent) == 1
