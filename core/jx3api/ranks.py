"""JX3API 榜单域：名剑、跨服名剑、武林争霸、悬赏、帮会/阵营/其他排行、试炼与资历排行。（自 core/jx3api_data.py 拆分，逻辑未改动）
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

ROLE_RANK_NAMES = {
    "名士五十强",
    "老江湖五十强",
    "兵甲藏家五十强",
    "名师五十强",
    "阵营英雄五十强",
    "薪火相传五十强",
    "庐园广记一百强",
}
TONG_RANK_NAMES0 = {
    "赛季恶人五十强",
    "赛季浩气五十强",
    "本周恶人五十强",
    "本周浩气五十强",
}
TONG_RANK_NAMES1 = {
    "浩气神兵宝甲五十强",
    "恶人神兵宝甲五十强",
    "浩气爱心帮会五十强",
    "恶人爱心帮会五十强",
}
TONG_RANK_NAMES2 = {
    "上周恶人五十强",
    "上周浩气五十强",
}

GUILD_RANK_OPTIONS = {
    "1": "浩气神兵宝甲五十强",
    "2": "恶人神兵宝甲五十强",
    "3": "浩气爱心帮会五十强",
    "4": "恶人爱心帮会五十强",
}
CAMP_RANK_OPTIONS = {
    "1": "赛季恶人五十强",
    "2": "赛季浩气五十强",
    "3": "上周恶人五十强",
    "4": "上周浩气五十强",
    "5": "本周恶人五十强",
    "6": "本周浩气五十强",
}
OTHER_RANK_OPTIONS = {
    "1": "名士五十强",
    "2": "老江湖五十强",
    "3": "兵甲藏家五十强",
    "4": "名师五十强",
    "5": "阵营英雄五十强",
    "6": "薪火相传五十强",
    "7": "庐园广记一百强",
}

RANK_NAMES = frozenset().union(
    ROLE_RANK_NAMES,
    TONG_RANK_NAMES0,
    TONG_RANK_NAMES1,
    TONG_RANK_NAMES2,
)


class RanksMixin:
    async def mingjianpaihang(self, limit: str, mode:str) -> Dict[str, Any]:
        """名剑排行"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["lists"] = data
            
        return await self._request_api(
            path="/arena/awesome",
            params={"limit": limit, "mode":mode, "token": self.token, "ticket": self.ticket},
            processor=processor,
            template="mingjianpaihang.html"
        )          
    async def mingjiantongji(self, mode: str) -> Dict[str, Any]:
        """名剑统计"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = {
                "items": data,
                "mode": mode,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        return await self._request_api(
            path="/arena/schools",
            params={"mode": mode, "token": self.token, "ticket": self.ticket},
            processor=processor,
            template="mingjiantongji.html"
        )         
    async def kuafumingjian(self, server: str, mode: int = 1) -> Dict[str, Any]:
        """跨服名剑榜。"""
        mode_names = {0: "2v2", 1: "3v3", 2: "5v5"}

        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            items = data.get("data") or []
            if not isinstance(items, list):
                items = []

            return_data["data"] = {
                "items": [item for item in items if isinstance(item, dict)],
                "name": data.get("name") or "跨服名剑榜",
                "server": data.get("server") or server or "全区",
                "mode_name": mode_names[mode],
                "update_time": format_time(data.get("time")),
            }

        return await self._request_api(
            path="/rank/arena",
            params={"server": server, "mode": mode, "token": self.token},
            processor=processor,
            template="kuafumingjian.html",
        )
    async def wulinzhengba(self, server: str, camp: int = 1) -> Dict[str, Any]:
        """武林争霸赛帮会榜。"""
        camp_names = {1: "浩气盟", 2: "恶人谷"}

        def format_match_time(value: Any) -> str:
            try:
                total_seconds = int(value)
            except (TypeError, ValueError):
                return ""
            if total_seconds < 0:
                return ""

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                return f"{hours}时{minutes:02d}分{seconds:02d}秒"
            return f"{minutes}分{seconds:02d}秒"

        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            items = data.get("data") or []
            if not isinstance(items, list):
                items = []

            rank_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                rank_item = item.copy()
                rank_item["lastMatchTimeText"] = format_match_time(
                    item.get("lastMatchTime")
                )
                rank_items.append(rank_item)

            return_data["data"] = {
                "items": rank_items,
                "name": data.get("name") or "武林争霸赛",
                "server": data.get("server") or server or "全区",
                "camp_name": camp_names[camp],
                "update_time": format_time(data.get("time")),
            }

        return await self._request_api(
            path="/rank/championship",
            params={"server": server, "camp": camp, "token": self.token},
            processor=processor,
            template="wulinzhengba.html",
        )
    async def _bounty_rank(self,server: str,path: str,fallback_name: str,show_hostile_count: bool,) -> Dict[str, Any]:
        """处理捕快荣誉和江湖浪客共用的榜单结构。"""

        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            items = data.get("data") or []
            if not isinstance(items, list):
                items = []

            return_data["data"] = {
                "items": [item for item in items if isinstance(item, dict)],
                "name": data.get("name") or fallback_name,
                "server": data.get("server") or server or "全区",
                "show_hostile_count": show_hostile_count,
                "update_time": format_time(data.get("time")),
            }

        return await self._request_api(
            path=path,
            params={"server": server, "token": self.token},
            processor=processor,
            template="bounty_rank.html",
        )
    async def bukairongyu(self, server: str) -> Dict[str, Any]:
        """捕快荣誉榜。"""
        return await self._bounty_rank(
            server=server,
            path="/rank/constable",
            fallback_name="捕快荣誉榜",
            show_hostile_count=False,
        )
    async def jianghulangke(self, server: str) -> Dict[str, Any]:
        """江湖浪客榜。"""
        return await self._bounty_rank(
            server=server,
            path="/rank/outlaw",
            fallback_name="江湖浪客榜",
            show_hostile_count=True,
        )
    async def juedoutiaozhan(self,server: str,mode: int = 1,) -> Dict[str, Any]:
        """决斗挑战榜。"""
        mode_names = {1: "公开", 2: "私密"}

        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            items = data.get("data") or []
            if not isinstance(items, list):
                items = []

            now_timestamp = int(datetime.now().timestamp())
            rank_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                rank_item = item.copy()
                try:
                    timeout = int(item.get("timeOut"))
                except (TypeError, ValueError):
                    remaining_time = ""
                else:
                    remaining_time = (
                        format_remaining(timeout)
                        if timeout > now_timestamp
                        else "已结束"
                    )
                rank_item["remainingTime"] = remaining_time
                rank_items.append(rank_item)

            return_data["data"] = {
                "items": rank_items,
                "name": data.get("name") or "决斗挑战榜",
                "server": data.get("server") or server or "全区",
                "mode_name": mode_names[mode],
                "update_time": format_time(data.get("time")),
            }

        return await self._request_api(
            path="/rank/wanted",
            params={"server": server, "mode": mode, "token": self.token},
            processor=processor,
            template="juedoutiaozhan.html",
        )
    async def banghui_rank_menu(self) -> Dict[str, str]:
        """帮会排行榜选择内容。"""
        return GUILD_RANK_OPTIONS.copy()
    async def zhenying_rank_menu(self) -> Dict[str, str]:
        """阵营排行榜选择内容。"""
        return CAMP_RANK_OPTIONS.copy()
    async def qita_rank_menu(self) -> Dict[str, str]:
        """其他排行榜选择内容。"""
        return OTHER_RANK_OPTIONS.copy()
    async def rank_statistical_select(self, server: str, selected: Dict[str, Any],) -> Dict[str, Any]:
        """排行榜次轮：根据单项选择数据查询对应榜单。"""
        if not isinstance(selected, dict) or len(selected) != 1:
            return_data = self._init_return_data()
            return_data["msg"] = "排行榜选项数据格式异常"
            return return_data

        rank_name = str(next(iter(selected.values())) or "").strip()
        if rank_name not in RANK_NAMES:
            return_data = self._init_return_data()
            return_data["msg"] = "无效排行榜选项"
            return return_data

        return await self.rank_statistical(rank_name, server)
    async def rank_statistical(self, name: str, server: str) -> Dict[str, Any]:
        """排行榜单"""

        if name in ROLE_RANK_NAMES:
            template_name = "rank_role.html"
        elif name in TONG_RANK_NAMES0:
            template_name = "rank_tong0.html"
        elif name in TONG_RANK_NAMES1:
            template_name = "rank_tong1.html"
        elif name in TONG_RANK_NAMES2:
            template_name = "rank_tong2.html"

        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            items = data.get("data") or []
            if isinstance(items, list):
                items = items[:50]
            else:
                items = []

            return_data["data"] = {
                "items": items,
                "server": data.get("server", server),
                "rank_name": data.get("name", name),
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        return await self._request_api(
            path="/rank/statistics",
            params={"server": server, "name": name, "token": self.token},
            processor=processor,
            template=template_name
        )   
    async def shilianpaixing(self, name: str, server: str) -> Dict[str, Any]:
        """试炼排行"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            items = data.get("data", [])

            return_data["data"] = {
                "items": items,
                "name": data.get("name", name),
                "server": data.get("server", server),
                "update_time": format_time(data.get("time"))
            }
            
        return await self._request_api(
            path="/rank/trials",
            params={"server": server,"name": name,"token": self.token,},
            processor=processor,
            template="shilianpaixing.html"
        )   
    async def zilipaixing(self,server: str, school: str) -> Dict[str, Any]:
        """资历排行"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = {
                "items": data,
                "school": school,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        return await self._request_api(
            path="/school/seniority",
            params= {"server": server,"school": school,"ticket": self.ticket,"token": self.token,},
            processor=processor,
            template="zilipaixing.html"
        ) 
