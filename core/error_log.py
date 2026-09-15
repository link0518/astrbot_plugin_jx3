"""错误日志面板：集中收集指令、接口与推送异常，供管理页直接查看。

设计约束：
- 记录失败必须静默，绝不影响业务流程；
- 内存 ring buffer 保留最近 ``BUFFER_CAPACITY`` 条供快速展示，
  SQLite 表保留最近 ``DB_KEEP_ROWS`` 条供重启后回看；
- 写入方负责脱敏（如事件推送侧已剔除 token 后再记录）。
"""

import time
from collections import deque
from typing import Any

from .sqlite import AsyncSQLiteDB

BUFFER_CAPACITY = 50
DB_KEEP_ROWS = 200
MAX_SUMMARY_LENGTH = 200
MAX_DETAIL_LENGTH = 500


class ErrorLogService:
    """错误日志的写入、查询与清理。"""

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite
        self._buffer: deque[dict[str, Any]] = deque(maxlen=BUFFER_CAPACITY)

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS error_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_error_log_time
            ON error_log(created_at)
            """
        )
        await self._trim()
        rows = await self.sql.fetch_all(
            """
            SELECT source, summary, detail, created_at
            FROM error_log
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (BUFFER_CAPACITY,),
        )
        self._buffer.clear()
        self._buffer.extend(rows)

    async def record(self, source: Any, summary: Any, detail: Any = ""):
        """写入一条错误日志；任何失败都静默吞掉。"""
        try:
            source = str(source or "").strip()[:32] or "未知"
            summary = str(summary or "").strip()[:MAX_SUMMARY_LENGTH]
            if not summary:
                return
            detail = str(detail or "")[:MAX_DETAIL_LENGTH]
            entry = {
                "source": source,
                "summary": summary,
                "detail": detail,
                "created_at": int(time.time()),
            }
            self._buffer.appendleft(entry)
            await self.sql.execute(
                """
                INSERT INTO error_log (source, summary, detail, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source, summary, detail, entry["created_at"]),
            )
            # 低频惰性裁剪，避免表无限增长。
            if len(self._buffer) == BUFFER_CAPACITY:
                await self._trim()
        except Exception:
            pass

    async def _trim(self):
        """SQLite 侧只保留最近 DB_KEEP_ROWS 条。"""
        await self.sql.execute(
            """
            DELETE FROM error_log
            WHERE id NOT IN (
                SELECT id FROM error_log
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            )
            """,
            (DB_KEEP_ROWS,),
        )

    async def list_recent(self, limit: int = BUFFER_CAPACITY) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or BUFFER_CAPACITY), DB_KEEP_ROWS))
        return await self.sql.fetch_all(
            """
            SELECT source, summary, detail, created_at
            FROM error_log
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def clear(self) -> int:
        row = await self.sql.fetch_one("SELECT COUNT(*) AS c FROM error_log")
        await self.sql.execute("DELETE FROM error_log")
        self._buffer.clear()
        return int(row.get("c") or 0) if row else 0
