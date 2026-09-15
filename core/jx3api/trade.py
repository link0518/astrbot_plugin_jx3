"""JX3API 交易域：阵营拍卖、的卢、金价、物价、成本、编号、花价与贴吧物价。（自 core/jx3api_data.py 拆分，逻辑未改动）
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

class TradeMixin:
    async def zhengyingpaimai(self, server: str, name: str, limit: int) -> Dict[str, Any]:
        """阵营拍卖"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["time"] =  format_time(item["time"])
            return_data["data"]["list"] = data
            
        return await self._request_api(
            path="/auction/records",
            params={"server": server, "name": name, "limit": limit, "token": self.token},
            processor=processor,
            template="zhengyingpaimai.html"
        )           
    async def dilujilu(self, server: str) -> Dict[str, Any]:
        """的卢拍卖"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["refreshTime"] = format_time(item["refreshTime"]) 
                item["captureTime"] = format_time(item["captureTime"])
                item["auctionTime"] = format_time(item["auctionTime"])
            return_data["data"]["list"] = data
            
        return await self._request_api(
            path="/steed/records",
            params={"server": server, "token": self.token},
            processor=processor,
            template="dilujilu.html"
        ) 
    async def jinjia(self, server: str, limit:str) -> Dict[str, Any]:
        """金价行情"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["items"] = data
            
        return await self._request_api(
            path="/trade/demon",
            params={"server": server, "limit": limit, "token": self.token},
            processor=processor,
            template="jinjia.html"
        ) 
    async def wujia(self, Name: str, server:str) -> Dict[str, Any]:
        """物价查询"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = data
            
        return await self._request_api(
            path="/trade/records",
            params={"name": Name,"token": self.token, "server": server},
            processor=processor,
            template="wujia.html"
        ) 
    async def chengbeng(self, Name: str, server:str, source: int) -> Dict[str, Any]:
        """成本计算"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = data
            
        return await self._request_api(
            path="/trade/manufacture",
            params={"name": Name,"token": self.token, "server": server, "source": source},
            processor=processor,
            template="chengbeng.html"
        ) 
    async def bianhao(self, id: str) -> Dict[str, Any]:
        """编号搜索"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            if not isinstance(data, dict):
                return_data["data"] = "账号角色数据格式错误"
                return

            # 同时兼容完整接口数据和直接传入 data 字段
            data = data.get("data", data)

            if not isinstance(data, dict):
                return_data["data"] = "账号角色数据为空"
                return

            # 将 replyContent 中的 HTML 转换为纯文本
            detail = str(data.get("replyContent") or "")
            detail = re.sub(r"<br\s*/?>", "\n", detail, flags=re.IGNORECASE)
            detail = re.sub(r"<[^>]+>", "", detail)
            detail = html.unescape(detail).strip() or "暂无账号详细信息"

            # 交易状态
            trade_status = {
                1: "公示中",
                2: "出售中",
                3: "出售中",
                4: "已售出",
                5: "已下架",
            }.get(data.get("tradeStatus"), f"状态码 {data.get('tradeStatus', '未知')}")

            # 调价记录，接口中的时间为毫秒时间戳
            update_prices = data.get("updatePrices") or []
            update_price_text = "\n".join(
                f"{index}. {format_time(int(item.get('updateTime') or 0) // 1000)}："
                f"{item.get('updatePrice', 0)} 元"
                for index, item in enumerate(update_prices, start=1)
                if isinstance(item, dict)
            ) or "暂无调价记录"

            return_data["data"] = (
                f"【万宝楼账号】\n"
                f"{data.get('replyTitle') or '暂无标题'}\n\n"

                f"【角色信息】\n"
                f"区服：{data.get('serverName') or '未知'}\n"
                f"角色：{data.get('roleName') or '未知'}\n"
                f"等级：{data.get('roleLevel') or 0}\n"
                f"门派：{data.get('forceName') or '未知'}\n"
                f"体型：{data.get('bodyName') or '未知'}\n"
                f"阵营：{data.get('campName') or '未知'}\n\n"

                f"【账号数据】\n"
                f"装备分数：{data.get('equipScore') or 0}\n"
                f"江湖资历：{data.get('seniorityNum') or 0}\n"
                f"约见次数：{data.get('meetingNum') or 0}\n"
                f"关注人数：{data.get('followNum') or 0}\n\n"

                f"【交易信息】\n"
                f"挂牌价格：{data.get('priceNum') or 0} 元\n"
                f"交易状态：{trade_status}\n"
                f"商品编号：{data.get('id') or '未知'}\n"
                f"发布时间：{format_time(data.get('replyTime') or 0)}\n\n"

                f"【调价记录】\n"
                f"{update_price_text}\n\n"

                f"【账号详情】\n"
                f"{detail}"
            )
            
        return await self._request_api(
            path="/trade/wanbaolou",
            params={"id": id,"token": self.token},
            processor=processor,
            template=""
        ) 
    async def huajia(self,server: str, name: str, map: str) -> Dict[str, Any]:
        """家园鲜花"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["data"] = data
            return_data["data"]["server"] = server

        return await self._request_api(
            path="/home/flower",
            params= {"server": server, "name": name,  "map": map},
            processor=processor,
            template="huajia.html"
        ) 
    async def tiebawujia(self, name: str, server: str, limit: int ) -> Dict[str, Any]:
        """贴吧物价"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            lines = [
                f"贴吧物价：{name}",
                f"服务器：{server}",
                f"记录数：{len(data)}",
                "",
            ]

            for index, item in enumerate(data, start=1):
                if not isinstance(item, dict):
                    continue

                item_time = item.get("time", "")
                if item_time:
                    try:
                        item_time = datetime.fromtimestamp(int(item_time)).strftime("%Y-%m-%d %H:%M:%S")
                    except (TypeError, ValueError, OSError):
                        item_time = str(item_time)

                lines.extend([
                    f"{index}. {item.get('name', '')}",
                    f"区服：{item.get('zone', '')}  服务器：{item.get('server', '')}",
                    f"内容：{item.get('context', '')}",
                    f"回复：{item.get('reply', '')}  楼层：{item.get('floor', '')}",
                    f"时间：{item_time}",
                    f"链接：https://tieba.baidu.com/p/{item.get('url', '')}",
                    "",
                ])

            if len(lines) <= 4:
                return_data["msg"] = "未查询到贴吧物价记录"
                return return_data

            return_data["data"] = "\n".join(lines).rstrip()

        return await self._request_api(
            path="/tieba/item/records",
            params= {"server": server,"name": name,"limit": limit,"token": self.token,},
            processor=processor,
            template=""
        ) 
