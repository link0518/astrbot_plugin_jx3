from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from astrbot.api.star import Context
from astrbot.api.web import error_response, json_response, request

from .event_push import EVENT_NAMES, FREE_EVENT_ACTIONS

if TYPE_CHECKING:
    from .access_control import AccessControlService
    from .bilei_data import BiLeidata
    from .cache import CacheService
    from .event_push import EventPushService
    from .jx3api_data import JX3APIService
    from .kungfu_alias import KungfuAliasService
    from .server_binding import ServerBindingService


class WebUIService:
    """注册插件管理页接口，并处理 WebUI 的数据读写。"""

    def __init__(
        self,
        jx3api: JX3APIService,
        event_push: EventPushService,
        server_binding: ServerBindingService,
        kungfu_alias: KungfuAliasService,
        bilei: BiLeidata,
        cache: CacheService,
        access_control: AccessControlService | None = None,
        group_name_backfill=None,
    ):
        self.jx3api = jx3api
        self.event_push = event_push
        self.server_binding = server_binding
        self.kungfu_alias = kungfu_alias
        self.bilei = bilei
        self.cache = cache
        self.access_control = access_control
        self.group_name_backfill = group_name_backfill

    def register(self, context: Context, plugin_name: str):
        routes = (
            ("dashboard", self.dashboard, ["GET"], "读取会话管理数据"),
            (
                "subscriptions/save",
                self.save_subscription,
                ["POST"],
                "保存会话事件推送配置",
            ),
            (
                "subscriptions/delete",
                self.delete_subscription,
                ["POST"],
                "删除会话事件推送配置",
            ),
            ("bindings/save", self.save_binding, ["POST"], "保存会话区服绑定"),
            ("bindings/delete", self.delete_binding, ["POST"], "删除会话区服绑定"),
            ("aliases/save", self.save_aliases, ["POST"], "保存区服别名"),
            ("aliases/delete", self.delete_aliases, ["POST"], "删除区服别名"),
            ("aliases/restore", self.restore_aliases, ["POST"], "恢复默认区服别名"),
            ("kungfu/save", self.save_kungfu, ["POST"], "保存心法别名"),
            ("kungfu/restore", self.restore_kungfu, ["POST"], "恢复默认心法别名"),
            (
                "bilei/legacy/migrate",
                self.migrate_legacy_bilei,
                ["POST"],
                "迁移旧避雷记录到指定会话",
            ),
            ("cache/settings/save", self.save_cache_setting, ["POST"], "保存缓存时间"),
            ("cache/limits/save", self.save_cache_limits, ["POST"], "保存缓存容量限制"),
            ("cache/item/clear", self.clear_cache_item, ["POST"], "清理单项缓存"),
            ("cache/clear", self.clear_cache, ["POST"], "清理查询缓存"),
            ("access/config", self.save_access_config, ["POST"], "保存插件使用范围配置"),
            ("access/entries/add", self.add_access_entry, ["POST"], "添加使用范围名单条目"),
            ("access/entries/delete", self.delete_access_entry, ["POST"], "删除使用范围名单条目"),
            ("access/groups/names/refresh", self.refresh_group_names, ["POST"], "批量补抓缺失的群名"),
            ("access/diagnostics", self.access_diagnostics, ["GET"], "诊断授权管理数据状态"),
        )
        for path, handler, methods, description in routes:
            context.register_web_api(
                f"/{plugin_name}/{path}",
                handler,
                methods,
                description,
            )

    @staticmethod
    async def _json_payload() -> dict[str, Any]:
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            raise ValueError("请求正文必须是 JSON 对象")
        return payload

    @staticmethod
    def _parse_aliases(raw_aliases: Any) -> list[str]:
        if isinstance(raw_aliases, str):
            return re.split(r"[,，;；\n]+", raw_aliases)
        if isinstance(raw_aliases, list):
            return [str(value) for value in raw_aliases]
        raise ValueError("别名必须是字符串或数组")

    async def dashboard(self):
        (
            bindings,
            subscriptions,
            aliases,
            kungfu,
            legacy_bilei,
            token_stats,
            cache,
        ) = await asyncio.gather(
            self.server_binding.list_bindings(),
            self.event_push.list_subscription_statuses(),
            self.server_binding.list_aliases(),
            self.kungfu_alias.list_kungfu(),
            self.bilei.list_legacy_records(),
            self.jx3api.token_stats(),
            self.cache.dashboard(),
        )
        access = None
        if self.access_control is not None:
            access_status = await self.access_control.get_status()
            access = {
                **access_status,
                "entries": await self.access_control.list_entries(),
                "recent_groups": await self.access_control.list_recent_groups(),
            }
        return json_response(
            {
                "bindings": bindings,
                "subscriptions": subscriptions,
                "aliases": aliases,
                "kungfu": kungfu,
                "servers": [item["server"] for item in aliases],
                "events": {str(action): name for action, name in EVENT_NAMES.items()},
                "free_event_actions": sorted(FREE_EVENT_ACTIONS),
                "legacy_bilei": legacy_bilei,
                "token_stats": token_stats,
                "cache": cache,
                "access": access,
            }
        )

    async def save_access_config(self):
        """保存插件使用范围配置（模式、私聊开关、拒绝提示开关）。"""
        if self.access_control is None:
            return error_response("使用范围服务未启用", status_code=503)
        payload = await self._json_payload()
        try:
            await self.access_control.set_config(
                mode=payload.get("mode"),
                private_allowed=payload.get("private_allowed"),
                reply_on_deny=payload.get("reply_on_deny"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def add_access_entry(self):
        """添加或更新一条使用范围名单条目。"""
        if self.access_control is None:
            return error_response("使用范围服务未启用", status_code=503)
        payload = await self._json_payload()
        try:
            await self.access_control.add_entry(
                str(payload.get("key") or ""),
                str(payload.get("note") or ""),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def access_diagnostics(self):
        """诊断授权管理三张表（access_entries / group_names / access_sessions）的当前状态。"""
        if self.access_control is None:
            return error_response("使用范围服务未启用", status_code=503)
        return json_response(await self.access_control.diagnostics())

    async def refresh_group_names(self):
        """批量补抓缺失的群名（通过插件侧缓存的 QQ 连接）。"""
        if self.group_name_backfill is None:
            return error_response("群名抓取不可用", status_code=503)
        try:
            updated = await self.group_name_backfill()
        except RuntimeError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"updated": updated})

    async def delete_access_entry(self):
        """删除一条使用范围名单条目。"""
        if self.access_control is None:
            return error_response("使用范围服务未启用", status_code=503)
        payload = await self._json_payload()
        key = str(payload.get("key") or "")
        if not key.strip():
            return error_response("会话 ID / 群号不能为空", status_code=400)
        await self.access_control.delete_entry(key)
        return json_response({"deleted": True})

    async def save_subscription(self):
        try:
            payload = await self._json_payload()
            await self.event_push.save_subscription(
                payload.get("session_id"),
                payload.get("enabled"),
                payload.get("actions"),
                payload.get("mode"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_subscription(self):
        try:
            payload = await self._json_payload()
            await self.event_push.delete_subscription(payload.get("session_id"))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def save_binding(self):
        try:
            payload = await self._json_payload()
            server = self.server_binding.resolve_standard_server(payload.get("server"))
            if not server:
                raise ValueError("绑定区服必须选择标准区服")
            await self.server_binding.set_binding(
                str(payload.get("session_id") or ""),
                server,
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_binding(self):
        try:
            payload = await self._json_payload()
            session_id = str(payload.get("session_id") or "")
            if not session_id.strip():
                raise ValueError("会话 ID 不能为空")
            await self.server_binding.delete_binding(session_id)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def save_aliases(self):
        try:
            payload = await self._json_payload()
            await self.server_binding.set_aliases(
                str(payload.get("server") or ""),
                self._parse_aliases(payload.get("aliases", [])),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def delete_aliases(self):
        try:
            payload = await self._json_payload()
            server = str(payload.get("server") or "")
            if not server.strip():
                raise ValueError("标准区服名不能为空")
            await self.server_binding.delete_aliases(server)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"deleted": True})

    async def restore_aliases(self):
        try:
            restored = await self.server_binding.restore_default_aliases()
        except (RuntimeError, ValueError) as exc:
            return error_response(str(exc), status_code=500)
        return json_response({"restored": restored})

    async def save_kungfu(self):
        try:
            payload = await self._json_payload()
            await self.kungfu_alias.save_aliases(
                payload.get("pzid"),
                self._parse_aliases(payload.get("aliases", [])),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def restore_kungfu(self):
        try:
            restored = await self.kungfu_alias.restore_defaults()
        except (RuntimeError, ValueError) as exc:
            return error_response(str(exc), status_code=500)
        return json_response({"restored": restored})

    async def migrate_legacy_bilei(self):
        try:
            payload = await self._json_payload()
            await self.bilei.migrate_legacy_record(
                payload.get("id"),
                payload.get("session_id"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"migrated": True})

    async def save_cache_setting(self):
        try:
            payload = await self._json_payload()
            await self.cache.set_ttl(
                str(payload.get("cache_type") or ""),
                str(payload.get("cache_name") or ""),
                payload.get("ttl_seconds"),
                payload.get("inherit") is True,
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def save_cache_limits(self):
        try:
            payload = await self._json_payload()
            await self.cache.set_limits(
                payload.get("api_memory_max_mb"),
                payload.get("api_max_entries"),
                payload.get("image_max_mb"),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"saved": True})

    async def clear_cache_item(self):
        try:
            payload = await self._json_payload()
            removed = await self.cache.clear_item(
                str(payload.get("cache_type") or ""),
                str(payload.get("cache_name") or ""),
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"cleared": True, "removed": removed})

    async def clear_cache(self):
        try:
            payload = await self._json_payload()
            removed = await self.cache.clear(str(payload.get("cache_type") or ""))
        except ValueError as exc:
            return error_response(str(exc), status_code=400)
        return json_response({"cleared": True, "removed": removed})
