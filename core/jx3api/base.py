"""JX3API 数据服务基座：HTTP 请求、两级缓存、令牌统计与标准返回结构。（自 core/jx3api_data.py 拆分，逻辑未改动）
"""
import json
import html
import re
import hashlib
import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any, Optional, List, Union
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Dict, Optional

from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from ..request import APIClient, APIErrorResponse
from ..sqlite import AsyncSQLiteDB
from ..fun_basic import load_template,gold_to_parts,week_to_num,compare_date_str,format_time,format_remaining

if TYPE_CHECKING:
    from ..cache import CacheService

class BaseService:
    def __init__(
        self,
        config: AstrBotConfig,
        sqlite: AsyncSQLiteDB,
        cache: Optional["CacheService"] = None,
    ):
        # 引用插件配置文件
        self._config = config
        # 仅显式配置为 false 时关闭证书验证，旧配置默认安全开启。
        self._api: APIClient = APIClient(
            ssl_verify=self._config.get("tls_verify", True) is not False
        )
        # 引用sqlite
        self._sql_db = sqlite
        self._cache = cache
        self._token_stats_cache: tuple[float, Dict[str, Any]] | None = None
        self._token_stats_lock = asyncio.Lock()
        # 获取配置中的 Token
        self.token = self._config.get("jx3api_token", "")
        if  self.token == "":
            logger.warning("获取配置token失败，请正确填写token,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置token成功。")
        # 获取配置中的 ticket
        self.ticket = self._config.get("jx3api_ticket", "")
        if  self.ticket == "":
            logger.warning("获取配置ticket失败，请正确填写ticket,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置ticket成功。")
        
    async def close(self):
        """释放底层 APIClient 资源"""
        if self._api:
            await self._api.close()
    async def server_list(self, force_refresh: bool = False) -> list[str]:
        """获取当前有效区服名称，供会话绑定和参数消歧使用。"""
        data, _ = await self._cached_request(
            "/server/status/check",
            {"server": "", "type": "其他"},
            force_refresh=force_refresh,
        )
        if not isinstance(data, list):
            return []
        return sorted(
            {
                str(item.get("server") or "").strip()
                for item in data
                if isinstance(item, dict) and item.get("server")
            }
        )
    async def token_stats(self) -> Optional[Dict[str, Any]]:
        """读取令牌统计；短时内存复用，避免 WebUI 保存配置时重复请求。"""
        if not str(self.token or "").strip():
            return None
        now = time.monotonic()
        if self._token_stats_cache and self._token_stats_cache[0] > now:
            return dict(self._token_stats_cache[1])

        async with self._token_stats_lock:
            now = time.monotonic()
            if self._token_stats_cache and self._token_stats_cache[0] > now:
                return dict(self._token_stats_cache[1])
            result = await self._fetch_token_stats()
            if result is not None:
                self._token_stats_cache = (now + 30, dict(result))
            return result
    async def _fetch_token_stats(self) -> Optional[Dict[str, Any]]:
        """查询当前配置 JX3API Token 的等级、用量及有效状态。"""
        if not str(self.token or "").strip():
            return None

        async def requester():
            return await self._api.post(
                "https://www.jx3api.com/token/stats",
                data={"token": self.token},
                out_key="data",
                success_codes=(200, "200"),
                return_error=True,
            )

        try:
            data = await requester()
        except Exception as exc:
            logger.warning(f"查询 JX3API Token 统计失败: {exc}")
            return None

        if isinstance(data, APIErrorResponse):
            logger.warning(
                f"JX3API Token 统计返回错误: "
                f"code={data.code}, msg={data.message or '未知错误'}"
            )
            return None
        if not isinstance(data, dict):
            return None

        def nonnegative_int(value: Any) -> Optional[int]:
            if isinstance(value, bool):
                return None
            try:
                number = int(value)
            except (TypeError, ValueError):
                return None
            return number if number >= 0 else None

        valid = data.get("valid")
        return {
            "level": nonnegative_int(data.get("level")),
            "used": nonnegative_int(data.get("used")),
            "remaining": nonnegative_int(data.get("remaining")),
            "valid": valid if isinstance(valid, bool) else None,
        }
    def _init_return_data(self) -> Dict[str, Any]:
            """初始化标准的返回数据结构"""
            return {
                "code": 0,
                "msg": "功能函数未执行",
                "data": {},
                "temp": "",
                "icons": {}
            }

    
    async def _base_request(
        self, 
        api_path: str, 
        params: Optional[Dict[str, Any]] = None, 
        out: Optional[str] = "data"
    ) -> Optional[Any]:
        """
        基础请求封装，处理配置获取和API调用。
        """
        try:
            if not self._api:
                logger.error("API client is not initialized")
                return None

            base_url = "https://www.jx3api.com"
            api_url = base_url + api_path
            data = await self._api.get(
                api_url,
                params=params,
                out_key=out,
                success_codes=(200, "200"),
                return_error=True,
            )
            
            if not data:
                logger.warning(f"获取接口信息失败或返回空数据: {api_url}")
            
            return data
            
        except Exception as e:
            logger.error(f"基础请求调用出错 ({api_path}): {e}")
            return None

    @staticmethod
    def _is_cacheable_response(data: Any) -> bool:
        return data is not None and not isinstance(data, APIErrorResponse)
    async def _cached_request(
        self,
        api_path: str,
        params: Optional[Dict[str, Any]] = None,
        out: Optional[str] = "data",
        force_refresh: bool = False,
    ) -> tuple[Any, dict[str, Any]]:
        request_params = params or {}
        if not self._cache:
            return await self._base_request(api_path, request_params, out), {
                "endpoint": api_path,
                "hit": False,
                "stale": False,
                "ttl_seconds": 0,
            }

        cache_params = dict(request_params)
        credential_values = [
            str(value)
            for key, value in request_params.items()
            if str(key).lower() in {"token", "ticket"} and value
        ]
        if credential_values:
            cache_params["__credential_scope"] = hashlib.sha256(
                "|".join(credential_values).encode("utf-8")
            ).hexdigest()

        try:
            return await self._cache.request_api(
                api_path,
                cache_params,
                lambda: self._base_request(api_path, request_params, out),
                self._is_cacheable_response,
                force_refresh=force_refresh,
            )
        except Exception as exc:
            logger.warning(f"接口缓存不可用，直接请求 JX3API endpoint={api_path}: {exc}")
            return await self._base_request(api_path, request_params, out), {
                "endpoint": api_path,
                "hit": False,
                "stale": False,
                "ttl_seconds": 0,
            }
    async def _request_api(
        self,
        path: str,
        params: Dict[str, Any],
        processor: Optional[
            Callable[[Any, Dict[str, Any]], Any | Awaitable[Any]]
        ] = None,
        template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """通用接口请求与模板处理。"""
        return_data = self._init_return_data()

        data, cache_metadata = await self._cached_request(path, params)
        return_data["_cache"] = cache_metadata
        if isinstance(data, APIErrorResponse):
            return_data["msg"] = data.message or "获取接口信息失败"
            return return_data
        if data is None:
            return_data["msg"] = "获取接口信息失败"
            return return_data

        try:
            await processor(data, return_data)
        except Exception as e:
            logger.exception(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data

        # template 为空时不加载模板
        if template:
            try:
                return_data["temp"] = await load_template(template)
            except FileNotFoundError as e:
                logger.error(f"加载模板失败: {e}")
                return_data["msg"] = "系统错误：模板文件不存在"
                return return_data

        return_data["code"] = 200
        return return_data

    # --- 业务功能函数 ---
    async def helps(self) -> Dict[str, Any]:
        """帮助"""
        return_data = self._init_return_data()
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("helps.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
            
        return_data["code"] = 200
   
        return return_data
