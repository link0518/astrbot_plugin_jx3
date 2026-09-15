"""指令执行分发单测：_call_with_auto_args 的参数转换与缺参校验。"""

from types import SimpleNamespace

import pytest

from astrbot_plugin_jx3.main import Jx3ApiPlugin

pytestmark = pytest.mark.asyncio

EVENT = SimpleNamespace(unified_msg_origin="default:GroupMessage:123")


async def _dispatch(handler, args):
    return await Jx3ApiPlugin._call_with_auto_args(
        SimpleNamespace(), handler, EVENT, args
    )


class TestCallWithAutoArgs:
    async def test_event_injected_and_positional_filled(self):
        # 真实 command_map 里是绑定方法，inspect.signature 不含 self。
        async def handler(event, name: str, server: str):
            return (event, name, server)

        event, name, server = await _dispatch(handler, ["晏卿卿", "梦江南"])
        assert event is EVENT
        assert (name, server) == ("晏卿卿", "梦江南")

    async def test_int_annotation_converted(self):
        async def handler(event, server: str, limit: int = 50):
            return limit

        assert await _dispatch(handler, ["梦江南", "20"]) == 20

    async def test_float_annotation_converted(self):
        async def handler(event, ratio: float = 1.0):
            return ratio

        assert await _dispatch(handler, ["1.5"]) == 1.5

    async def test_invalid_int_falls_back_to_default(self):
        """无法解析为 int 时回退默认值，不抛异常（3.4.6 行为）。"""
        async def handler(event, server: str, limit: int = 50):
            return limit

        assert await _dispatch(handler, ["梦江南", "abc"]) == 50

    async def test_missing_optional_uses_default(self):
        async def handler(event, server: str, mode: str = "33"):
            return mode

        assert await _dispatch(handler, ["梦江南"]) == "33"

    async def test_missing_required_raises_value_error(self):
        async def handler(event, server: str, name: str):
            return None

        with pytest.raises(ValueError, match="缺少参数"):
            await _dispatch(handler, ["梦江南"])

    async def test_self_parameter_skipped(self):
        """绑定方法场景：self 占位但不从 args 消费。"""

        class Handler:
            async def run(self, event, server: str):
                return server

        assert await _dispatch(Handler().run, ["梦江南"]) == "梦江南"
