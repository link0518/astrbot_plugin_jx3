"""主动推送的会话路由：解决多 QQ 账号共用同一 aiocqhttp 平台时的投递失败。

背景：AstrBot 的 aiocqhttp 适配器在「主动按 session 发送」时硬编码
``event=None``，不向 aiocqhttp 传递 ``self_id``；aiocqhttp 路由只能依赖
「恰好一条连接」的兜底。当多个账号反连到同一平台（多条 WS 挂在同一个
``_wsr_api_clients``）时兜底失效，抛出 ``ApiNotAvailable``，推送报「投递失败」。

本服务在任意消息事件经过时记录「会话 -> (bot, self_id, 目标)」：
``self_id`` 取自该会话自己的消息事件，天然就是该群/该好友可见的账号。
推送时按会话显式携带 ``self_id`` 定向发送；拿不到路由（冷启动、非
aiocqhttp 连接）时回退框架默认发送。路由记录是内存态（bot 连接对象无法
持久化），连接断开重连后会随新消息事件自动刷新。
"""

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain


class PushRouter:
    """按会话缓存连接与发送账号，提供带 self_id 的定向发送。"""

    def __init__(self, context):
        self.context = context
        # {unified_msg_origin: {"bot":..., "self_id": str, "is_group": bool, "target": int}}
        self._routes: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _call_action(bot):
        """探测 bot 的 call_action：aiocqhttp 直接挂在 bot 上（无 .api 层），
        个别实现可能挂在 bot.api 上，两级兼容，取不到返回 None。"""
        action = getattr(bot, "call_action", None)
        if callable(action):
            return action
        api = getattr(bot, "api", None)
        action = getattr(api, "call_action", None)
        return action if callable(action) else None

    def record(self, event: AstrMessageEvent) -> None:
        """从任意消息事件捕获会话路由；非 aiocqhttp 连接或字段缺失直接跳过。"""
        session_id = getattr(event, "unified_msg_origin", "") or ""
        if not session_id:
            return
        bot = getattr(event, "bot", None)
        if bot is None or self._call_action(bot) is None:
            return
        message_obj = getattr(event, "message_obj", None)
        self_id = getattr(message_obj, "self_id", None)
        if self_id in (None, ""):
            return
        group_id = str(event.get_group_id() or "").strip()
        target_text = group_id if group_id else str(event.get_sender_id() or "").strip()
        if not target_text.isdigit():
            return
        self._routes[session_id] = {
            "bot": bot,
            "self_id": str(self_id),
            "is_group": bool(group_id),
            "target": int(target_text),
        }

    def drop(self, session_id: str) -> None:
        """丢弃某会话的路由（例如连接对象已失效）。"""
        self._routes.pop(session_id, None)

    def has_route(self, session_id: str) -> bool:
        return session_id in self._routes

    async def send(self, session_id: str, text: str) -> None:
        """按会话定向发送；无路由时回退框架默认发送。

        路由命中时不再回退：显式携带的 ``self_id`` 若失效（账号离线/退群），
        回退到框架默认发送同样会失败且掩盖真实原因，故直接抛出交由上层记录。
        """
        route = self._routes.get(session_id)
        call_action = self._call_action(route["bot"]) if route else None
        if route is None or call_action is None:
            if route is not None:
                # 连接对象已失去 call_action（适配器重载等），清掉脏路由再回退。
                self.drop(session_id)
            await self._fallback_send(session_id, text)
            return

        message = [{"type": "text", "data": {"text": text}}]
        if route["is_group"]:
            await call_action(
                "send_group_msg",
                group_id=route["target"],
                message=message,
                self_id=route["self_id"],
            )
        else:
            await call_action(
                "send_private_msg",
                user_id=route["target"],
                message=message,
                self_id=route["self_id"],
            )
        logger.debug(f"主动推送已按路由发送：session={session_id}, self_id={route['self_id']}")

    async def _fallback_send(self, session_id: str, text: str) -> None:
        message_chain = MessageChain().message(text)
        await self.context.send_message(session_id, message_chain)
