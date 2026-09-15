"""错误日志服务单测：写入、缓冲回填、裁剪、清空、容错。"""

import pytest

from astrbot_plugin_jx3.core.error_log import (
    BUFFER_CAPACITY,
    DB_KEEP_ROWS,
    ErrorLogService,
)
from astrbot_plugin_jx3.core.sqlite import AsyncSQLiteDB


@pytest.fixture()
async def service(tmp_path):
    db = AsyncSQLiteDB(str(tmp_path / "errors.db"))
    await db.connect()
    svc = ErrorLogService(db)
    await svc.initialize()
    yield svc
    await db.close()


class TestRecord:
    async def test_record_persists_and_buffered(self, service):
        await service.record("指令", "战绩: APIError: 超时", "参数: 双梦 晏卿卿")
        rows = await service.list_recent()
        assert len(rows) == 1
        assert rows[0]["source"] == "指令"
        assert rows[0]["summary"] == "战绩: APIError: 超时"
        assert rows[0]["detail"] == "参数: 双梦 晏卿卿"
        # 内存缓冲同步可见
        assert service._buffer[0]["summary"] == rows[0]["summary"]

    async def test_blank_summary_ignored(self, service):
        await service.record("指令", "   ")
        assert await service.list_recent() == []

    async def test_lengths_truncated(self, service):
        await service.record("指令", "x" * 500, "y" * 1000)
        rows = await service.list_recent()
        assert len(rows[0]["summary"]) == 200
        assert len(rows[0]["detail"]) == 500

    async def test_recent_order_desc(self, service):
        for index in range(5):
            await service.record("推送", f"错误 {index}")
        rows = await service.list_recent()
        summaries = [row["summary"] for row in rows]
        assert summaries == [f"错误 {index}" for index in reversed(range(5))]

    async def test_buffer_capacity(self, service):
        for index in range(BUFFER_CAPACITY + 10):
            await service.record("指令", f"错误 {index}")
        assert len(service._buffer) == BUFFER_CAPACITY


class TestPersistence:
    async def test_buffer_reloaded_after_reopen(self, tmp_path):
        db_path = str(tmp_path / "reopen.db")
        db = AsyncSQLiteDB(db_path)
        await db.connect()
        svc = ErrorLogService(db)
        await svc.initialize()
        await svc.record("指令", "重启前的错误")
        await db.close()

        db2 = AsyncSQLiteDB(db_path)
        await db2.connect()
        svc2 = ErrorLogService(db2)
        await svc2.initialize()
        assert svc2._buffer[0]["summary"] == "重启前的错误"
        await db2.close()

    async def test_db_trimmed_to_keep_rows(self, service):
        for index in range(DB_KEEP_ROWS + 20):
            await service.record("指令", f"错误 {index}")
        await service._trim()
        row = await service.sql.fetch_one("SELECT COUNT(*) AS c FROM error_log")
        assert row["c"] == DB_KEEP_ROWS


class TestClear:
    async def test_clear(self, service):
        await service.record("指令", "错误 1")
        await service.record("推送", "错误 2")
        removed = await service.clear()
        assert removed == 2
        assert await service.list_recent() == []
        assert len(service._buffer) == 0
