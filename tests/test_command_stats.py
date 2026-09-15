"""指令使用统计服务单测：写入、聚合汇总、保留期清理、容错。"""

import time

import pytest

from astrbot_plugin_jx3.core.command_stats import (
    CommandStatsService,
    RETENTION_DAYS,
)
from astrbot_plugin_jx3.core.sqlite import AsyncSQLiteDB


@pytest.fixture()
async def service(tmp_path):
    db = AsyncSQLiteDB(str(tmp_path / "stats.db"))
    await db.connect()
    svc = CommandStatsService(db)
    await svc.initialize()
    yield svc
    await db.close()


async def _seed(service):
    await service.record("战绩", "s1", 1200, True)
    await service.record("战绩", "s1", 800, True)
    await service.record("战绩", "s2", 3000, False, "APIError: 上游超时")
    await service.record("沙盘", "s1", 500, True)
    await service.record("物价", "s2", 200, False, "ValueError: 缺少参数")


class TestRecord:
    async def test_record_persists(self, service):
        await service.record("战绩", "s1", 1234, True)
        row = await service.sql.fetch_one(
            "SELECT * FROM command_stats WHERE command=?", ("战绩",)
        )
        assert row["duration_ms"] == 1234
        assert row["ok"] == 1
        assert row["session_id"] == "s1"

    async def test_blank_command_ignored(self, service):
        await service.record("  ", "s1", 10, True)
        row = await service.sql.fetch_one("SELECT COUNT(*) AS c FROM command_stats")
        assert row["c"] == 0

    async def test_bad_duration_tolerated(self, service):
        await service.record("战绩", "s1", "not-a-number", True)
        row = await service.sql.fetch_one(
            "SELECT duration_ms FROM command_stats WHERE command=?", ("战绩",)
        )
        assert row["duration_ms"] == 0

    async def test_error_truncated(self, service):
        await service.record("战绩", "s1", 10, False, "x" * 500)
        row = await service.sql.fetch_one(
            "SELECT error FROM command_stats WHERE command=?", ("战绩",)
        )
        assert len(row["error"]) == 200


class TestSummary:
    async def test_totals(self, service):
        await _seed(service)
        stats = await service.summary(7)
        assert stats["total"] == 5
        assert stats["ok_count"] == 3
        assert stats["fail_count"] == 2
        assert stats["success_rate"] == 60.0

    async def test_top_commands_order_and_aggregation(self, service):
        await _seed(service)
        stats = await service.summary(7)
        top = stats["top_commands"]
        assert top[0]["command"] == "战绩"
        assert top[0]["calls"] == 3
        assert top[0]["fail_count"] == 1
        assert top[0]["avg_ms"] == (1200 + 800 + 3000) // 3

    async def test_slowest_requires_min_calls(self, service):
        await _seed(service)
        stats = await service.summary(7)
        commands = [item["command"] for item in stats["slowest"]]
        # 物价/沙盘只调用 1 次，不进慢查询榜
        assert commands == ["战绩"]
        assert stats["slowest"][0]["max_ms"] == 3000

    async def test_failure_top(self, service):
        await _seed(service)
        stats = await service.summary(7)
        failures = {item["command"]: item for item in stats["failure_top"]}
        assert failures["物价"]["fail_rate"] == 100
        assert failures["战绩"]["fail_count"] == 1

    async def test_recent_errors_desc(self, service):
        await _seed(service)
        stats = await service.summary(7)
        assert len(stats["recent_errors"]) == 2
        assert stats["recent_errors"][0]["created_at"] >= stats["recent_errors"][1]["created_at"]

    async def test_empty_summary(self, service):
        stats = await service.summary(7)
        assert stats["total"] == 0
        assert stats["success_rate"] is None

    async def test_days_window_excludes_old_records(self, service):
        old_ts = int(time.time()) - 10 * 86400
        await service.sql.execute(
            "INSERT INTO command_stats (command, session_id, duration_ms, ok, error, created_at)"
            " VALUES (?, '', 100, 1, '', ?)",
            ("老指令", old_ts),
        )
        stats = await service.summary(7)
        assert stats["total"] == 0
        stats = await service.summary(30)
        assert stats["total"] == 1


class TestCleanup:
    async def test_retention_cleanup(self, service):
        expired = int(time.time()) - (RETENTION_DAYS + 1) * 86400
        await service.sql.execute(
            "INSERT INTO command_stats (command, session_id, duration_ms, ok, error, created_at)"
            " VALUES (?, '', 100, 1, '', ?)",
            ("过期指令", expired),
        )
        await service.cleanup()
        row = await service.sql.fetch_one("SELECT COUNT(*) AS c FROM command_stats")
        assert row["c"] == 0

    async def test_clear(self, service):
        await _seed(service)
        removed = await service.clear()
        assert removed == 5
        row = await service.sql.fetch_one("SELECT COUNT(*) AS c FROM command_stats")
        assert row["c"] == 0
