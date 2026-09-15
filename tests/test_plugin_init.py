"""插件实例化冒烟测试：完整构造 Jx3ApiPlugin 必须成功。

 AstrBot 加载器的 try/except TypeError 回退会吞掉 __init__ 内部
抛出的 TypeError（转而报 "missing config"），任何构造链路上的
签名错误只有实例化测试能拦住。3.7.0 曾因此线上加载失败。
"""

import pytest

from astrbot.api import AstrBotConfig
from astrbot.api.star import Context

from astrbot_plugin_jx3.main import Jx3ApiPlugin

CONFIG = AstrBotConfig(
    {
        "jx3api_token": "",
        "jx3api_ticket": "",
        "jx3api_wss": "",
        "jx3api_wss_token": "",
        "prefix": {"enable": False, "text": ""},
        "image_render_quality": {},
        "tls_verify": True,
    }
)


def test_plugin_instantiates():
    """构造插件全链路（路径/base64/所有服务/WebUI 路由注册）无异常。"""
    context = Context()
    plugin = Jx3ApiPlugin(context, CONFIG)
    # WebUI 路由全部注册成功（含 stats / errors 新路由）
    paths = [item[0] for item in context.registered_web_apis]
    assert any(path.endswith("/stats") for path in paths)
    assert any(path.endswith("/errors") for path in paths)
    # 新服务接线完整
    assert plugin.command_stats is not None
    assert plugin.error_log is not None
    assert plugin.group_info is not None
    assert plugin.webui.command_stats is plugin.command_stats
    assert plugin.webui.error_log is plugin.error_log
    assert plugin.event_push.error_log is plugin.error_log
    assert plugin.webui.group_name_backfill == plugin.group_info.backfill


def test_plugin_command_map_requires_initialize():
    """command_map 在 initialize() 前为空，on_all_message 会忽略消息。"""
    plugin = Jx3ApiPlugin(Context(), CONFIG)
    assert plugin.command_map == {}
