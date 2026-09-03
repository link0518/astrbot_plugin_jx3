"""插件使用范围控制：按群 / 会话决定插件是否可用。

管理页可切换三种模式并维护名单，全部数据保存在本地 SQLite：

- ``all``（默认）：所有群和私聊均可使用，名单不生效。
- ``whitelist``：只有名单内的群可使用；私聊是否可用由独立开关决定。
- ``blacklist``：名单内的群被禁用，其余群可使用；私聊是否可用由独立开关决定。

名单条目既可以是完整会话标识（AstrBot ``unified_msg_origin``），
也可以是纯群号；判断时会话会同时用两者参与匹配。
"""

from typing import Any, Iterable, Optional

from .sqlite import AsyncSQLiteDB

MODE_ALL = "all"
MODE_WHITELIST = "whitelist"
MODE_BLACKLIST = "blacklist"
SUPPORTED_MODES = {MODE_ALL, MODE_WHITELIST, MODE_BLACKLIST}

# 拒绝原因
REASON_MODE = "mode"  # 群被名单规则拒绝
REASON_PRIVATE = "private"  # 私聊被独立开关关闭


class AccessControlService:
    """维护插件使用范围配置、名单与活跃会话记录。"""

    def __init__(self, sqlite: AsyncSQLiteDB):
        self.sql = sqlite
        self.mode = MODE_ALL
        self.private_allowed = True
        self.reply_on_deny = False
        self._entries: set[str] = set()

    # ======================
    # 生命周期
    # ======================

    async def initialize(self):
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS access_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS access_entries (
                key TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self.sql.execute(
            """
            CREATE TABLE IF NOT EXISTS access_sessions (
                session_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                group_id TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self._load()

    async def _load(self):
        self.mode = MODE_ALL
        self.private_allowed = True
        self.reply_on_deny = False

        rows = await self.sql.fetch_all("SELECT key, value FROM access_config")
        for row in rows:
            key = str(row.get("key") or "")
            value = str(row.get("value") or "").strip()
            if key == "mode" and value in SUPPORTED_MODES:
                self.mode = value
            elif key == "private_allowed":
                self.private_allowed = self._to_bool(value, default=True)
            elif key == "reply_on_deny":
                self.reply_on_deny = self._to_bool(value, default=False)

        entry_rows = await self.sql.fetch_all("SELECT key FROM access_entries")
        self._entries = {
            self._clean(row.get("key"))
            for row in entry_rows
            if self._clean(row.get("key"))
        }

    # ======================
    # 配置读写
    # ======================

    async def set_config(
        self,
        mode: Optional[str] = None,
        private_allowed: Optional[bool] = None,
        reply_on_deny: Optional[bool] = None,
    ):
        """更新使用范围配置；未提供的字段保持不变。"""
        if mode is not None:
            mode = self._clean(mode).casefold()
            if mode not in SUPPORTED_MODES:
                raise ValueError(f"不支持的使用范围模式：{mode}")
            await self._set_config_value("mode", mode)
            self.mode = mode

        if private_allowed is not None:
            private_allowed = self._to_bool(private_allowed, default=True)
            await self._set_config_value(
                "private_allowed", "1" if private_allowed else "0"
            )
            self.private_allowed = private_allowed

        if reply_on_deny is not None:
            reply_on_deny = self._to_bool(reply_on_deny, default=False)
            await self._set_config_value(
                "reply_on_deny", "1" if reply_on_deny else "0"
            )
            self.reply_on_deny = reply_on_deny

    async def _set_config_value(self, key: str, value: str):
        await self.sql.execute(
            """
            INSERT INTO access_config (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )

    async def get_status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "private_allowed": self.private_allowed,
            "reply_on_deny": self.reply_on_deny,
        }

    # ======================
    # 名单维护
    # ======================

    async def list_entries(self) -> list[dict[str, str]]:
        rows = await self.sql.fetch_all(
            "SELECT key, note, updated_at FROM access_entries "
            "ORDER BY updated_at DESC, key"
        )
        return [
            {
                "key": self._clean(row.get("key")),
                "note": self._clean(row.get("note")),
                "updated_at": str(row.get("updated_at") or ""),
            }
            for row in rows
        ]

    async def add_entry(self, key: Any, note: str = ""):
        key = self._clean(key)
        note = self._clean(note)
        if not key:
            raise ValueError("会话 ID / 群号不能为空")
        if len(key) > 512:
            raise ValueError("会话 ID / 群号过长")
        if len(note) > 64:
            raise ValueError("备注最长 64 个字符")

        await self.sql.execute(
            """
            INSERT INTO access_entries (key, note, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE
            SET note=excluded.note, updated_at=CURRENT_TIMESTAMP
            """,
            (key, note),
        )
        self._entries.add(key)

    async def delete_entry(self, key: Any):
        key = self._clean(key)
        if not key:
            raise ValueError("会话 ID / 群号不能为空")
        await self.sql.delete("access_entries", "key=?", (key,))
        self._entries.discard(key)

    # ======================
    # 活跃会话记录（供管理页识别群、供推送侧判断会话类型）
    # ======================

    async def record_usage(self, session_id: Any, group_id: Any):
        """记录一次插件指令来源会话。群消息记录 kind=group 与群号，
        私聊记录 kind=private；管理页可据此列出“最近活跃的群”。"""
        session_id = self._clean(session_id)
        if not session_id or len(session_id) > 512:
            return
        group_id = self._clean(group_id)
        kind = "group" if group_id else "private"
        await self.sql.execute(
            """
            INSERT INTO access_sessions (session_id, kind, group_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE
            SET kind=excluded.kind,
                group_id=excluded.group_id,
                updated_at=CURRENT_TIMESTAMP
            """,
            (session_id, kind, group_id),
        )

    async def list_recent_groups(self, limit: int = 60) -> list[dict[str, str]]:
        """最近触发过本插件指令的群（每个群取最新一次会话）。"""
        limit = max(1, min(int(limit), 200))
        rows = await self.sql.fetch_all(
            """
            SELECT group_id, session_id, updated_at
            FROM access_sessions
            WHERE kind='group' AND group_id<>''
              AND session_id=(
                  SELECT latest.session_id FROM access_sessions AS latest
                  WHERE latest.group_id=access_sessions.group_id
                  ORDER BY latest.updated_at DESC
                  LIMIT 1
              )
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "group_id": self._clean(row.get("group_id")),
                "session_id": self._clean(row.get("session_id")),
                "updated_at": str(row.get("updated_at") or ""),
            }
            for row in rows
        ]

    async def session_allowed(self, session_id: Any) -> bool:
        """事件推送侧按会话判断是否允许投递。"""
        session_id = self._clean(session_id)
        if not session_id:
            return False
        row = await self.sql.select_one(
            "access_sessions", "session_id=?", (session_id,)
        )
        if row is None:
            # 升级前已存在的订阅没有类型记录，默认放行以避免推送消失；
            # 会话下次触发指令后会写入记录并纳入规则。
            return True
        kind = self._clean(row.get("kind"))
        group_id = self._clean(row.get("group_id"))
        if kind == "private":
            return self.private_allowed
        allowed, _ = self.is_allowed(session_id, group_id)
        return allowed

    # ======================
    # 判定
    # ======================

    def is_allowed(self, session_id: Any, group_id: Any) -> tuple[bool, str]:
        """返回 ``(是否允许, 拒绝原因)``。

        私聊只看 ``private_allowed``；群消息按当前模式与名单匹配。
        """
        group_id = self._clean(group_id)
        if not group_id:
            return (self.private_allowed, "" if self.private_allowed else REASON_PRIVATE)

        if self.mode == MODE_ALL:
            return True, ""

        candidates = self._candidates(session_id, group_id)
        in_list = any(candidate in self._entries for candidate in candidates)

        if self.mode == MODE_WHITELIST:
            return (True, "") if in_list else (False, REASON_MODE)
        # blacklist
        return (False, REASON_MODE) if in_list else (True, "")

    def deny_text(self, reason: str) -> str:
        """拒绝时回复给会话的提示文案。"""
        if reason == REASON_PRIVATE:
            return "本插件的私聊功能已被管理员停用，请在已启用的群内使用。"
        if self.mode == MODE_WHITELIST:
            return "当前群未启用本插件功能，如需使用请联系管理员在插件管理页中开启。"
        return "当前群已被管理员停用本插件功能。"

    @staticmethod
    def _candidates(session_id: Any, group_id: Any) -> set[str]:
        """名单匹配候选：完整会话标识与纯群号都参与匹配。"""
        candidates: set[str] = set()
        session_id = AccessControlService._clean(session_id)
        group_id = AccessControlService._clean(group_id)
        if session_id:
            candidates.add(session_id)
        if group_id:
            candidates.add(group_id)
        return candidates

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        normalized = AccessControlService._clean(value).casefold()
        if not normalized:
            return default
        return normalized in {"1", "true", "yes", "on", "y", "是", "开"}
