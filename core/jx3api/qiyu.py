"""JX3API 奇遇域：个人奇遇、未出、汇总、近期与统计。（自 core/jx3api_data.py 拆分，逻辑未改动）
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

class QiyuMixin:
    async def qiyuhuizong(self, server: str, num: int) -> Dict[str, Any]:
        """奇遇汇总"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                latest = item.get("last")
                item["latest_name"] = latest.get("name")
                item["latest_time"] = format_time(latest.get("time"))

            return_data["data"] = {
                "items": data,
                "server": server,
                "num": num,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        return await self._request_api(
            path="/event/collect",
            params={"server": server, "num": num, "token": self.token},
            processor=processor,
            template="qiyuhuizong.html"
        ) 
    async def weizuoqiyu(self, server: str, name: str, ) -> Dict[str, Any]:
        """未出奇遇"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["ptqy"] = []
            return_data["data"]["jsqy"] = []
            return_data["data"]["name"] = name
            return_data["data"]["server"] = server

            for item in data:
                try:
                    level = int(item.get("level", 0))
                except (TypeError, ValueError):
                    continue

                event_item = {
                    "event": item.get("name"),
                    "time": "未触发"
                }

                if level == 1:
                    return_data["data"]["ptqy"].append(event_item)
                elif level == 2:
                    return_data["data"]["jsqy"].append(event_item)

            if not return_data["data"]["ptqy"] and not return_data["data"]["jsqy"]:
                return_data["msg"] = "未查询到未做普通或绝世奇遇"
                return return_data
            
        return await self._request_api(
            path="/event/missing",
            params={"server": server, "name": name, "token": self.token},
            processor=processor,
            template="weizuoqiyu.html"
        ) 
    async def jinqiqiyu(self, server: str, limit: int) -> Dict[str, Any]:
        """近期奇遇"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["time"] = format_time(item.get("time"))

            return_data["data"] = {
                "items": data,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        return await self._request_api(
            path="/event/recent",
            params={"server": server, "limit": limit, "token": self.token},
            processor=processor,
            template="jinqiqiyu.html"
        ) 

    
    async def juesheqiyu(self, server: str, name: str, full: int) -> Dict[str, Any]:
        """角色奇遇"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["ptqy"] = []
            return_data["data"]["jsqy"] = []
            return_data["data"]["cwqy"] = []

            for item in data:
                item["time"] = datetime.fromtimestamp(item["time"]).strftime("%Y-%m-%d %H:%M:%S")
                if item["level"] == 1:
                    return_data["data"]["ptqy"].append(item)
                if item["level"] == 2:
                    return_data["data"]["jsqy"].append(item)
                if item["level"] == 3:
                    return_data["data"]["cwqy"].append(item)
            
        return await self._request_api(
            path="/event/records",
            params= {"server": server, "name": name, "full": full, "token": self.token},
            processor=processor,
            template="juesheqiyu.html"
        ) 
    async def qiyutongji(self, name: str, server: str, limit: int) -> Dict[str, Any]:
        """奇遇统计"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["time"] = format_time(item.get("time"))

            return_data["data"] = {
                "items": data,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "qiyuname": name
            }

        return await self._request_api(
            path="/event/statistics",
            params={"name": name, "server": server, "limit": limit, "token": self.token},
            processor=processor,
            template="qiyuliebiao.html"
        ) 
