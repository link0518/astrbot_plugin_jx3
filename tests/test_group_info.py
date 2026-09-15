"""群名解析服务单测：call_action 探测、缓存 TTL、失败回退与批量补抓。"""

import time
from types import SimpleNamespace

import pytest

from astrbot_plugin_jx3.core.access_control import AccessControlService
from astrbot_plugin_jx3.core.group_info import (
    GROUP_NAME_FAIL_TTL,
    GROUP_NAME_TTL,
    GroupInfoService,
)
from astrbot_plugin_jx3.core.sqlite import AsyncSQLiteDB


class FakeBot:
    """aiocqhttp 风格：call_action 直接挂在 bot 上。"""

    def __init__(self, names=None, fail=False):
        self.names = dict(names or {})
        self.fail = fail
        self.calls = []

    async def call_action(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if self.fail:
            raise RuntimeError("get_group_info failed")
        return {"group_name": self.names.get(kwargs.get("group_id"), "")}


class FakeApiBot:
    """兼容形态：call_action 挂在 bot.api 上。"""

    def __init__(self, inner):
        self.api = inner


@pytest.fixture()
async def service(tmp_path):
    db = AsyncSQLiteDB(str(tmp_path / "groups.db"))
    await db.connect()
    access = AccessControlService(db)
    await access.initialize()
    svc = GroupInfoService(access)
    yield svc
    await db.close()


def _event(bot=None, self_id=None):
    return SimpleNamespace(
        bot=bot,
        message_obj=SimpleNamespace(self_id=self_id),
    )


class TestCallActionProbe:
    def test_direct_on_bot(self):
        bot = FakeBot()
        action = GroupInfoService._bot_call_action(bot)
        # 绑定方法每次访问都是新对象，比较底层函数与绑定实例
        assert action.__func__ is FakeBot.call_action
        assert action.__self__ is bot

    def test_on_bot_api(self):
        inner = FakeBot()
        bot = FakeApiBot(inner)
        action = GroupInfoService._bot_call_action(bot)
        assert action.__func__ is FakeBot.call_action
        assert action.__self__ is inner

    def test_missing_returns_none(self):
        assert GroupInfoService._bot_call_action(object()) is None
        assert GroupInfoService._bot_call_action(None) is None


class TestResolve:
    async def test_success_caches_name(self, service):
        bot = FakeBot({10001: "测试群"})
        name = await service.resolve(_event(bot), "10001")
        assert name == "测试群"
        # 缓存命中：第二次不再调用 call_action
        name = await service.resolve(_event(bot), "10001")
        assert name == "测试群"
        assert len(bot.calls) == 1

    async def test_empty_group_id_short_circuits(self, service):
        bot = FakeBot()
        assert await service.resolve(_event(bot), "") == ""
        assert bot.calls == []

    async def test_no_bot_returns_empty(self, service):
        assert await service.resolve(_event(None), "10001") == ""

    async def test_failure_cached_with_short_ttl(self, service):
        bot = FakeBot(fail=True)
        assert await service.resolve(_event(bot), "10001") == ""
        name, ts = service._cache["10001"]
        assert name == ""
        # 失败记录 10 分钟内直接返回，不重复请求
        assert await service.resolve(_event(bot), "10001") == ""
        assert len(bot.calls) == 1
        # 成功 TTL 与失败 TTL 区分
        assert GROUP_NAME_FAIL_TTL < GROUP_NAME_TTL

    async def test_event_caches_connection_for_backfill(self, service):
        bot = FakeBot()
        await service.resolve(_event(bot, self_id=999), "10001")
        assert service._bot is bot
        assert service._self_id == 999


class TestBackfill:
    async def test_backfill_updates_missing(self, service):
        bot = FakeBot({10001: "补抓群", 10002: ""})
        service._bot = bot
        await service.access_control.record_usage("s1", "10001", "")
        await service.access_control.record_usage("s2", "10002", "")
        result = await service.backfill()
        assert result == {"updated": 1, "missing": 2, "failed": 1}
        names = await service.access_control.get_session_group_names(["s1"])
        assert names["s1"] == "补抓群"

    async def test_backfill_without_connection_raises(self, service):
        with pytest.raises(RuntimeError, match="暂未获取到 QQ 连接"):
            await service.backfill()

    async def test_routing_self_id_passed(self, service):
        bot = FakeBot({10001: "群"})
        service._bot = bot
        service._self_id = 999
        await service.access_control.record_usage("s1", "10001", "")
        await service.backfill()
        assert bot.calls[0][1]["self_id"] == 999

    async def test_expired_success_refetched(self, service):
        bot = FakeBot({10001: "旧名"})
        service._cache["10001"] = ("旧名", time.monotonic() - GROUP_NAME_TTL - 1)
        bot.names[10001] = "新名"
        name = await service.resolve(_event(bot), "10001")
        assert name == "新名"
