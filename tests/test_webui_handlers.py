"""WebUI handler 级测试：统计接口参数解析与请求桩接口面。"""

import pytest

from astrbot_plugin_jx3.core import webui as webui_mod
from astrbot_plugin_jx3.core.command_stats import CommandStatsService
from astrbot_plugin_jx3.core.sqlite import AsyncSQLiteDB
from astrbot_plugin_jx3.core.webui import WebUIService


@pytest.fixture()
async def stats_service(tmp_path):
    db = AsyncSQLiteDB(str(tmp_path / "stats.db"))
    await db.connect()
    svc = CommandStatsService(db)
    await svc.initialize()
    yield svc
    await db.close()


@pytest.fixture()
def ui(stats_service):
    return WebUIService(None, None, None, None, None, None, command_stats=stats_service)


@pytest.fixture(autouse=True)
def _reset_request_stub():
    yield
    webui_mod.request.set_query()
    webui_mod.request.json_payload = {}


class TestStatsSummaryHandler:
    async def test_default_days(self, ui, stats_service):
        await stats_service.record("战绩", "s1", 1000, True)
        webui_mod.request.set_query()
        resp = await ui.command_stats_summary()
        assert resp["ok"] is True
        data = resp["data"]
        assert data["days"] == 7
        assert data["total"] == 1

    async def test_days_from_query(self, ui):
        webui_mod.request.set_query(days="30")
        resp = await ui.command_stats_summary()
        assert resp["ok"] is True
        assert resp["data"]["days"] == 30

    async def test_invalid_days_falls_back(self, ui):
        webui_mod.request.set_query(days="abc")
        resp = await ui.command_stats_summary()
        assert resp["ok"] is True
        assert resp["data"]["days"] == 7

    async def test_service_disabled(self):
        ui = WebUIService(None, None, None, None, None, None, command_stats=None)
        resp = await ui.command_stats_summary()
        assert resp["ok"] is False


class TestRequestStubContract:
    """请求桩接口面：提供 query/json，不提供 args。"""

    def test_stub_has_no_args_attr(self):
        assert not hasattr(webui_mod.request, "args")

    def test_stub_query_get(self):
        webui_mod.request.set_query(days="14")
        assert webui_mod.request.query.get("days", "7") == "14"
        assert webui_mod.request.query.get("missing", "7") == "7"
        webui_mod.request.set_query()

    async def test_stub_json_default(self):
        webui_mod.request.json_payload = None
        assert await webui_mod.request.json(default={}) == {}
        webui_mod.request.json_payload = {"a": 1}
        assert await webui_mod.request.json(default={}) == {"a": 1}
