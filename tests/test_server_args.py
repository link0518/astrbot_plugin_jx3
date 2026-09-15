"""参数准备层单测：_prepare_server_args / _prepare_kungfu_args。

重点覆盖 3.4.4 修复的回归：绑定区服后省略服务器、直接填后续
可选参数时不能被误判为显式服务器。
"""

from types import SimpleNamespace

import pytest

from astrbot_plugin_jx3.main import Jx3ApiPlugin

pytestmark = pytest.mark.asyncio


class FakeBinding:
    """ServerBindingService 最小替身（内存版）。"""

    def __init__(self, bound: str = "", known=(), aliases=None):
        self._bound = bound
        self._known = set(known)
        self._aliases = dict(aliases or {})

    async def get_binding(self, session_id: str) -> str:
        return self._bound

    def is_all_servers_query(self, value) -> bool:
        return str(value or "").strip() == "全区"

    def is_known_server(self, value) -> bool:
        # 与真实实现一致：标准区服与别名都算"已知区服"（_server_lookup 含别名键）。
        value = str(value or "").strip()
        return value in self._known or value in self._aliases

    def resolve_query_server(self, value) -> str:
        value = str(value or "").strip()
        if value == "全区":
            return ""
        return self._aliases.get(value, value)


class FakeKungfuAlias:
    def __init__(self, mapping=None):
        self._mapping = dict(mapping or {})

    def resolve_kungfu(self, value):
        return self._mapping.get(value, value)


class _FakePlugin:
    """把被测方法挂为类属性以获得正确的 self 绑定。"""

    _prepare_server_args = Jx3ApiPlugin._prepare_server_args
    _prepare_kungfu_args = Jx3ApiPlugin._prepare_kungfu_args

    def __init__(self, bound="", known=("梦江南", "唯我独尊"), aliases=None, kungfu_map=None):
        self.server_binding = FakeBinding(bound, known, aliases or {"双梦": "梦江南"})
        self.kungfu_alias = FakeKungfuAlias(kungfu_map or {"冰心": "冰心诀"})


def _fake(bound="", known=("梦江南", "唯我独尊"), aliases=None, kungfu_map=None):
    return _FakePlugin(bound, known, aliases, kungfu_map)


async def handler_zhanji(self, event, name: str, server: str, mode: str = "33"):
    """战绩式签名：name 在 server 之前。"""


async def handler_machang(self, event, server: str, expired: int = 0):
    """马场式签名：server 是第一个参数。"""


async def handler_no_server(self, event, limit: int = 10):
    """无 server 参数的签名。"""


EVENT = SimpleNamespace(unified_msg_origin="default:GroupMessage:123")


class TestPrepareServerArgs:
    async def test_no_binding_resolves_alias(self):
        fake = _fake()
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿", "双梦"]
        )
        assert args == ["晏卿卿", "梦江南"]

    async def test_bound_server_inserted_when_omitted(self):
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿"]
        )
        assert args == ["晏卿卿", "梦江南"]

    async def test_bound_server_optional_arg_not_misjudged(self):
        """3.4.4 回归：绑定后 `战绩 晏卿卿 22`，"22" 不是区服，
        应补齐绑定区服并把 22 留给 mode。"""
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿", "22"]
        )
        assert args == ["晏卿卿", "梦江南", "22"]

    async def test_explicit_server_wins_over_binding(self):
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿", "唯我独尊"]
        )
        assert args == ["晏卿卿", "唯我独尊"]

    async def test_explicit_alias_resolved_over_binding(self):
        fake = _fake(bound="唯我独尊")
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿", "双梦"]
        )
        assert args == ["晏卿卿", "梦江南"]

    async def test_all_servers_keyword_overrides_binding(self):
        """`全区` 保留值：即使已绑定也传空区服查全区。"""
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(
            handler_zhanji, EVENT, ["晏卿卿", "全区"]
        )
        assert args == ["晏卿卿", ""]

    async def test_server_first_signature_insert(self):
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(handler_machang, EVENT, [])
        assert args == ["梦江南"]

    async def test_no_server_param_untouched(self):
        fake = _fake(bound="梦江南")
        args = await fake._prepare_server_args(handler_no_server, EVENT, ["5"])
        assert args == ["5"]


class TestPrepareKungfuArgs:
    async def test_alias_resolved(self):
        async def handler(self, event, kungfu: str, update: int = 0):
            pass

        fake = _fake()
        args = fake._prepare_kungfu_args(handler, ["冰心"])
        assert args == ["冰心诀"]

    async def test_standard_name_kept(self):
        async def handler(self, event, kungfu: str, update: int = 0):
            pass

        fake = _fake()
        assert fake._prepare_kungfu_args(handler, ["云裳心经"]) == ["云裳心经"]

    async def test_no_kungfu_param_untouched(self):
        fake = _fake()
        assert fake._prepare_kungfu_args(handler_zhanji, ["晏卿卿", "梦江南"]) == [
            "晏卿卿",
            "梦江南",
        ]

    async def test_missing_kungfu_arg_untouched(self):
        async def handler(self, event, kungfu: str, update: int = 0):
            pass

        fake = _fake()
        assert fake._prepare_kungfu_args(handler, []) == []
