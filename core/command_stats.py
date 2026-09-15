"""指令使用统计：记录每条指令的耗时与成败，供管理页「指令统计」页签展示。

设计约束：
- 记录失败必须静默，绝不能影响指令主流程；
- ``ok=False`` 仅用于插件侧异常（接口失败、渲染错误等），
  用户参数错误（ValueError 分支）不计入失败，避免污染失败率；
- 数据保留 ``RETENTION_DAYS`` 天，初始化与查询汇总时惰性清理。
"""

import time
from typing import Any

from .sqlite import AsyncSQLiteDB

MAX_ERROR_LENGTH = 200
RECENT_ERRORS_LIMIT = 20
RETENTION_DAYS = 90


class CommandStatsService:
    """指令调用统计的写入与聚合查询。"""

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS command_stats(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                duration_ms INTEGER NOT NULL DEFAULT 0,
                ok INTEGER NOT NULL DEFAULT 1,
                error TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_command_stats_cmd
            ON command_stats(command, created_at)
            """
        )
        await self.sql.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_command_stats_time
            ON command_stats(created_at)
            """
        )
        await self.cleanup()

    async def record(
        self,
        command: Any,
        session_id: Any,
        duration_ms: Any,
        ok: bool,
        error: str = "",
    ):
        """写入一条调用记录；任何失败都静默吞掉。"""
        try:
            command = str(command or "").strip()[:64]
            if not command:
                return
            session_id = str(session_id or "").strip()[:512]
            try:
                duration = max(0, int(duration_ms))
            except (TypeError, ValueError):
                duration = 0
            await self.sql.execute(
                """
                INSERT INTO command_stats
                    (command, session_id, duration_ms, ok, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    command,
                    session_id,
                    duration,
                    1 if ok else 0,
                    str(error or "")[:MAX_ERROR_LENGTH],
                    int(time.time()),
                ),
            )
        except Exception:
            pass

    async def cleanup(self):
        """清除超过保留期的历史记录。"""
        cutoff = int(time.time()) - RETENTION_DAYS * 86400
        try:
            await self.sql.execute(
                "DELETE FROM command_stats WHERE created_at < ?", (cutoff,)
            )
        except Exception:
            pass

    async def clear(self) -> int:
        """清空全部统计，返回删除行数（管理页「清空统计」）。"""
        row = await self.sql.fetch_one("SELECT COUNT(*) AS c FROM command_stats")
        await self.sql.execute("DELETE FROM command_stats")
        return int(row.get("c") or 0) if row else 0

    async def summary(self, days: int = 7) -> dict[str, Any]:
        """聚合近 ``days`` 天的统计，供 WebUI 展示。"""
        days = max(1, min(int(days or 7), RETENTION_DAYS))
        await self.cleanup()
        since = int(time.time()) - days * 86400

        totals = await self.sql.fetch_one(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(ok), 0) AS ok_count,
                   COALESCE(AVG(duration_ms), 0) AS avg_ms
            FROM command_stats
            WHERE created_at >= ?
            """,
            (since,),
        ) or {}

        top_commands = await self.sql.fetch_all(
            """
            SELECT command,
                   COUNT(*) AS calls,
                   COALESCE(SUM(ok), 0) AS ok_count,
                   COUNT(*) - COALESCE(SUM(ok), 0) AS fail_count,
                   CAST(AVG(duration_ms) AS INTEGER) AS avg_ms
            FROM command_stats
            WHERE created_at >= ?
            GROUP BY command
            ORDER BY calls DESC, command
            LIMIT 50
            """,
            (since,),
        )

        slowest = await self.sql.fetch_all(
            """
            SELECT command,
                   COUNT(*) AS calls,
                   CAST(AVG(duration_ms) AS INTEGER) AS avg_ms,
                   MAX(duration_ms) AS max_ms
            FROM command_stats
            WHERE created_at >= ?
            GROUP BY command
            HAVING calls >= 2
            ORDER BY avg_ms DESC, command
            LIMIT 10
            """,
            (since,),
        )

        failure_top = await self.sql.fetch_all(
            """
            SELECT command,
                   COUNT(*) AS calls,
                   COUNT(*) - COALESCE(SUM(ok), 0) AS fail_count,
                   CAST(100.0 * (COUNT(*) - COALESCE(SUM(ok), 0)) / COUNT(*) AS INTEGER) AS fail_rate
            FROM command_stats
            WHERE created_at >= ?
            GROUP BY command
            HAVING fail_count > 0
            ORDER BY fail_count DESC, command
            LIMIT 10
            """,
            (since,),
        )

        recent_errors = await self.sql.fetch_all(
            """
            SELECT command, session_id, error, created_at
            FROM command_stats
            WHERE ok = 0
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (RECENT_ERRORS_LIMIT,),
        )

        total = int(totals.get("total") or 0)
        ok_count = int(totals.get("ok_count") or 0)
        return {
            "days": days,
            "total": total,
            "ok_count": ok_count,
            "fail_count": total - ok_count,
            "success_rate": round(100.0 * ok_count / total, 1) if total else None,
            "avg_ms": int(totals.get("avg_ms") or 0),
            "top_commands": top_commands,
            "slowest": slowest,
            "failure_top": failure_top,
            "recent_errors": recent_errors,
        }
