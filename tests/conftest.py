"""pytest 公共夹具：stub 掉 AstrBot / aiocqhttp 运行时依赖。

插件本体运行在 AstrBot 进程内，大量模块在 import 期就引用
``astrbot.api.*`` / ``astrbot.core.*`` / ``aiocqhttp.*``。
单测不启动 AstrBot，这里用最小 stub 满足 import，
使 main.py 与 core/ 各模块可以在纯 Python 环境下加载。
"""

import logging
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 路径：插件目录本身即包 astrbot_plugin_jx3，把其父目录加入 sys.path
# ---------------------------------------------------------------------------
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT.parent))


def _module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _identity_decorator(*args, **kwargs):
    """把 @register(...) / @filter.event_message_type(...) 变成无操作装饰器。"""

    def wrap(func):
        return func

    return wrap


# ---------------------------------------------------------------------------
# astrbot stub
# ---------------------------------------------------------------------------
logger = logging.getLogger("jx3plugin-test")

astrbot_mod = _module("astrbot")
astrbot_mod.logger = logger

api_mod = _module("astrbot.api")
api_mod.logger = logger


class AstrBotConfig(dict):
    """配置即字典，插件通过 .get(...) 读取。"""


api_mod.AstrBotConfig = AstrBotConfig
astrbot_mod.api = api_mod

# astrbot.api.event ----------------------------------------------------------
event_mod = _module("astrbot.api.event")
api_mod.event = event_mod


class AstrMessageEvent:  # 仅占位，测试中用 SimpleNamespace 伪造实例
    pass


class MessageChain:
    pass


class _EventMessageType:
    ALL = "ALL"


class _Filter:
    EventMessageType = _EventMessageType

    @staticmethod
    def event_message_type(*args, **kwargs):
        return _identity_decorator()


event_mod.AstrMessageEvent = AstrMessageEvent
event_mod.MessageChain = MessageChain
event_mod.filter = _Filter()

# astrbot.api.star -----------------------------------------------------------
star_mod = _module("astrbot.api.star")
api_mod.star = star_mod


class Context:
    """AstrBot Context 最小替身：管理页路由注册只记录不执行。"""

    def __init__(self):
        self.registered_web_apis = []

    def register_web_api(self, path, handler, methods, description):
        self.registered_web_apis.append((path, handler, methods, description))


class Star:
    def __init__(self, context):
        self.context = context


class StarTools:
    @staticmethod
    def get_data_dir(plugin_name: str) -> Path:
        path = PLUGIN_ROOT / ".workbuddy" / "tmp" / "test-data" / plugin_name
        path.mkdir(parents=True, exist_ok=True)
        return path


def register(*args, **kwargs):
    return _identity_decorator()


star_mod.Context = Context
star_mod.Star = Star
star_mod.StarTools = StarTools
star_mod.register = register

# astrbot.api.web ------------------------------------------------------------
web_mod = _module("astrbot.api.web")
api_mod.web = web_mod


def json_response(data=None, *args, **kwargs):
    return {"ok": True, "data": data}


def error_response(message="", *args, **kwargs):
    return {"ok": False, "message": message}


web_mod.json_response = json_response
web_mod.error_response = error_response


class _StubMultiDict:
    """键值对列表，get 取同名键的最后一个值。"""

    def __init__(self, pairs=()):
        self._pairs = list(pairs)

    def get(self, key, default=None):
        for item_key, item_value in reversed(self._pairs):
            if item_key == key:
                return item_value
        return default

    def getlist(self, key):
        return [value for item_key, value in self._pairs if item_key == key]


class _StubPluginRequest:
    """插件 Web 请求桩，接口对齐 PluginRequest（query/json/path_params）。"""

    def __init__(self):
        self.query = _StubMultiDict()
        self.json_payload = {}
        self.method = "GET"
        self.path = "/"
        self.path_params = {}
        self.plugin_name = None
        self.username = None

    async def json(self, default=None):
        return self.json_payload if self.json_payload is not None else default

    def set_query(self, **params):
        """整体替换查询参数。"""
        self.query = _StubMultiDict(list(params.items()))


web_mod.request = _StubPluginRequest()

# astrbot.api.message_components ---------------------------------------------
comp_mod = _module("astrbot.api.message_components")
api_mod.message_components = comp_mod


class _Comp:
    """消息组件占位：按属性名动态生成类型，避免运行期 AttributeError。"""

    def __getattr__(self, name):
        cls = type(name, (), {})
        setattr(self, name, cls)
        return cls


comp_mod.Plain = type("Plain", (), {})
comp_mod.Image = type("Image", (), {})

# astrbot.core ---------------------------------------------------------------
core_mod = _module("astrbot.core")
astrbot_mod.core = core_mod

html_renderer_mod = _module("astrbot.core.html_renderer")


async def _render_custom_template(*args, **kwargs):  # pragma: no cover - 不在单测中渲染
    raise RuntimeError("单测环境不支持 HTML 渲染")


html_renderer_mod.render_custom_template = _render_custom_template
core_mod.html_renderer = html_renderer_mod

core_utils_mod = _module("astrbot.core.utils")
core_mod.utils = core_utils_mod

session_waiter_mod = _module("astrbot.core.utils.session_waiter")
core_utils_mod.session_waiter = session_waiter_mod


class SessionController:
    pass


def session_waiter(*args, **kwargs):
    return _identity_decorator()


session_waiter_mod.SessionController = SessionController
session_waiter_mod.session_waiter = session_waiter

# ---------------------------------------------------------------------------
# aiocqhttp stub
# ---------------------------------------------------------------------------
aiocqhttp_mod = _module("aiocqhttp")
aiocqhttp_exc_mod = _module("aiocqhttp.exceptions")
aiocqhttp_mod.exceptions = aiocqhttp_exc_mod


class ActionFailed(Exception):
    pass


aiocqhttp_exc_mod.ActionFailed = ActionFailed


# ---------------------------------------------------------------------------
# 公共夹具
# ---------------------------------------------------------------------------


@pytest.fixture()
def plugin_pkg():
    """返回已加载的插件包（import 副作用已在 stub 下完成）。"""
    import astrbot_plugin_jx3  # noqa: PLC0415

    return astrbot_plugin_jx3
