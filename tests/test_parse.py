"""指令解析层单测：parse_message / resolve_command。

不实例化插件（__init__ 依赖 AstrBot 运行时），
把方法绑到只含所需属性的假对象上调用。
"""

from types import SimpleNamespace

from astrbot_plugin_jx3.main import Jx3ApiPlugin


class _FakePlugin:
    """把被测方法挂为类属性以获得正确的 self 绑定。"""

    parse_message = Jx3ApiPlugin.parse_message
    resolve_command = Jx3ApiPlugin.resolve_command

    def __init__(self, prefix=None, command_map=None):
        self.prefix = prefix or {"enable": False, "text": ""}
        self.command_map = command_map or {}


def _fake(prefix=None, command_map=None):
    return _FakePlugin(prefix, command_map)


def _event(processed: str, original: str | None = None):
    return SimpleNamespace(
        message_str=processed,
        message_obj=SimpleNamespace(
            message_str=processed if original is None else original
        ),
    )


class TestParseMessage:
    def setup_method(self):
        self.fake = _fake()

    def parse(self, text):
        return Jx3ApiPlugin.parse_message(self.fake, text)

    def test_plain_command(self):
        assert self.parse("战绩 双梦 晏卿卿") == ["战绩", "双梦", "晏卿卿"]

    def test_blank_returns_none(self):
        assert self.parse("") is None
        assert self.parse("   ") is None

    def test_prefix_disabled_ignores_prefix_config(self):
        self.fake.prefix = {"enable": False, "text": "jx3"}
        assert self.parse("战绩 双梦") == ["战绩", "双梦"]

    def test_prefix_enabled_strips_prefix(self):
        self.fake.prefix = {"enable": True, "text": "jx3"}
        assert self.parse("jx3 战绩 双梦") == ["战绩", "双梦"]

    def test_prefix_enabled_rejects_message_without_prefix(self):
        self.fake.prefix = {"enable": True, "text": "jx3"}
        assert self.parse("战绩 双梦") is None

    def test_empty_prefix_falls_back_to_no_prefix(self):
        """前缀开启但内容为空/纯空格时按未开启处理（3.4.6 行为）。"""
        for empty in ("", "   "):
            self.fake.prefix = {"enable": True, "text": empty}
            assert self.parse("战绩 双梦") == ["战绩", "双梦"]


class TestResolveCommand:
    def setup_method(self):
        async def handler(event):
            return None

        self.fake = _fake(command_map={"战绩": handler, "沙盘": handler})

    def resolve(self, processed, original=None):
        return Jx3ApiPlugin.resolve_command(self.fake, _event(processed, original))

    def test_hit_returns_command_args_handler(self):
        result = self.resolve("战绩 双梦 晏卿卿")
        assert result is not None
        cmd, args, handler = result
        assert cmd == "战绩"
        assert args == ["双梦", "晏卿卿"]
        assert handler is self.fake.command_map["战绩"]

    def test_miss_returns_none(self):
        assert self.resolve("今天天气怎么样") is None

    def test_falls_back_to_original_text(self):
        """AstrBot 处理后的文本不含指令时，用平台原始文本兜底。"""
        result = self.resolve("已处理文本", original="沙盘 双梦")
        assert result is not None
        assert result[0] == "沙盘"

    def test_duplicate_texts_scanned_once(self):
        assert self.resolve("战绩 双梦", original="战绩 双梦") is not None
