"""群名解析服务：经 aiocqhttp 的 get_group_info 抓取并缓存群名。

不依赖平台名判断（AstrBot 实例名可能是 default 或任意自定义名），
改为探测 bot 的 ``call_action`` 能力（aiocqhttp 即具备）。
成功缓存 24 小时、失败缓存 10 分钟；任何失败都静默回退为空串，
绝不阻塞指令主流程。
"""

import asyncio
import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

GROUP_NAME_TTL = 86400.0
GROUP_NAME_FAIL_TTL = 600.0
MAX_GROUP_NAME_LENGTH = 64


class GroupInfoService:
    """群名抓取、缓存与批量补抓。"""

    def __init__(self, access_control):
        self.access_control = access_control
        # {group_id: (name, monotonic 时间)}
        self._cache: dict[str, tuple[str, float]] = {}
        self._bot = None
        self._self_id = None

    @staticmethod
    def _bot_call_action(bot):
        """探测 bot 的 call_action：aiocqhttp 直接挂在 bot 上（无 .api 层），
        个别实现可能挂在 bot.api 上，两级兼容，取不到返回 None。"""
        action = getattr(bot, "call_action", None)
        if callable(action):
            return action
        api = getattr(bot, "api", None)
        action = getattr(api, "call_action", None)
        return action if callable(action) else None

    def _routing(self) -> dict[str, Any]:
        return {"self_id": self._self_id} if self._self_id else {}

    async def resolve(self, event: AstrMessageEvent, group_id: str) -> str:
        """解析群名供管理页展示；失败静默返回空串。"""
        bot = getattr(event, "bot", None)
        if bot is not None:
            # 只要消息事件带连接就缓存，供管理页「抓取群名」批量补抓使用。
            self._bot = bot
            self._self_id = getattr(event.message_obj, "self_id", None)
        if not group_id:
            return ""
        now = time.monotonic()
        cached = self._cache.get(group_id)
        if cached is not None:
            name, ts = cached
            ttl = GROUP_NAME_TTL if name else GROUP_NAME_FAIL_TTL
            if now - ts < ttl:
                return name
        name = ""
        call_action = self._bot_call_action(bot)
        if call_action is not None:
            try:
                info = await call_action(
                    "get_group_info", group_id=int(group_id), **self._routing()
                )
                name = str((info or {}).get("group_name") or "").strip()[
                    :MAX_GROUP_NAME_LENGTH
                ]
            except Exception as exc:
                logger.warning(f"获取群名失败（不影响指令执行）：group={group_id}, {exc}")
        else:
            logger.warning(
                f"获取群名失败：当前连接的 bot 不支持 call_action，group={group_id}"
            )
        self._cache[group_id] = (name, now)
        return name

    async def backfill(self, limit: int = 80) -> dict:
        """批量补抓缺失的群名（管理页「抓取群名」按钮）。
        返回 {"updated": 成功数, "missing": 缺失数, "failed": 失败数}。"""
        call_action = self._bot_call_action(self._bot)
        if call_action is None:
            raise RuntimeError("暂未获取到 QQ 连接，请先在任意会话（群聊/私聊）发一条消息再试")
        group_ids = await self.access_control.list_groups_missing_names(limit)
        updated, failed = 0, 0
        for group_id in group_ids:
            try:
                info = await call_action(
                    "get_group_info", group_id=int(group_id), **self._routing()
                )
                name = str((info or {}).get("group_name") or "").strip()[
                    :MAX_GROUP_NAME_LENGTH
                ]
            except Exception:
                name = ""
            if name:
                await self.access_control.update_group_name(group_id, name)
                self._cache[group_id] = (name, time.monotonic())
                updated += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)  # 温和限速，避免连续请求
        return {"updated": updated, "missing": len(group_ids), "failed": failed}
