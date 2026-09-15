"""JX3API 角色域：战绩、名片、精耐、百战、成就、资历、角色、发言、师徒与副本记录。（自 core/jx3api_data.py 拆分，逻辑未改动）
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

class RoleMixin:
    async def zhanji(self, name: str, server:str, mode:str) -> Dict[str, Any]:
        """战绩"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            performance_key = {
                "22": "2v2",
                "33": "3v3",
                "55": "5v5",
            }.get(str(mode), "3v3")
            data["currentPerformance"] = data["performance"][performance_key]
            return_data["data"] = data
            
        return await self._request_api(
            path="/arena/recent",
            params={"server": server, "name":name, "mode":mode, "token": self.token, "ticket": self.ticket},
            processor=processor,
            template="zhanji.html"
        )  
    async def jueshemingpian(self, server: str, name: str) -> Dict[str, Any]:
        """名片记录"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            url = data.get("showAvatar")
            if not url:
                return_data["msg"] = "未获取到名片图片"
                return return_data

            server_name = data.get("serverName", server)
            role_name = data.get("roleName", name)
            show_like = data.get("showLike", 0)
            msg0 = f"{server_name}-{role_name}"
            msg1 = f"点赞：{show_like}"

            return_data["data"] = [
                Comp.Plain(msg0),
                Comp.Image.fromURL(url),
                Comp.Plain(msg1)
            ]
            
        return await self._request_api(
            path="/card/record",
            params={"server": server, "name": name, "token": self.token},
            processor=processor,
            template=""
        ) 
    async def shuijimingpian(self, server:str, force: str, body:str,) -> Dict[str, Any]:
        """随机名片"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            url = data.get("showAvatar")
            if not url:
                return_data["msg"] = "未获取到名片图片"
                return return_data

            server_name = data.get("serverName")
            role_name = data.get("roleName")
            msg = f"{server_name}-{role_name}"

            return_data["data"] = [
                Comp.Plain(msg),
                Comp.Image.fromURL(url),
            ]
            
        return await self._request_api(
            path="/card/random",
            params={"server": server, "body": body, "force":force, "token": self.token},
            processor=processor,
            template=""
        ) 
    async def shuoyoumingpian(self, server: str, name: str) -> Dict[str, Any]:
        """名片历史"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            chain = []
            for m in data:
                status = "当前展示" if m.get("showActive") else "未展示"
                msg = f"第{m.get('showIndex')}张 {status}"
                url = m.get("showAvatar")

                if not url:
                    logger.warning(f"第{m.get('showIndex')}张名片缺少图片URL，已跳过")
                    continue

                chain.extend([
                    Comp.Plain(msg),
                    Comp.Image.fromURL(url),
                ])

            if not chain:
                return_data["msg"] = "未获取到有效的名片数据"
                return return_data

            return_data["data"] = chain

        return await self._request_api(
            path="/card/records",
            params={"server": server, "name": name, "token": self.token},
            processor=processor,
            template=""
        ) 
    async def jingnai(self, name: str, server: str) -> Dict[str, Any]:
        """角色百战"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            items = data.get("skillList", [])
            if not isinstance(items, list) or not items:
                return_data["msg"] = "未查询到技能信息"
                return return_data

            color_map = {
                7: "黑色",
                6: "紫色",
                5: "红色",
                4: "绿色",
                3: "蓝色",
                2: "黄色",
                0: "无",
            }

            for item in items:
                if not isinstance(item, dict):
                    continue

                color = item.get("nColor")
                try:
                    color_key = int(color)
                except (TypeError, ValueError):
                    color_key = None
                item["skill_color_text"] = color_map.get(color_key, str(color) if color is not None else "")

            return_data["data"] = {
                "server": data.get("server", server),
                "role_name": data.get("roleName", name),
                "skill_energy": data.get("skillEnergy", ""),
                "skill_stamina": data.get("skillStamina", ""),
                "skill_count": data.get("skillCount", len(items)),
                "items": items,
                "update_time": format_time( data.get("updateTime"))
            }

        return await self._request_api(
            path="/monster/records",
            params={"server": server, "name": name, "token": self.token},
            processor=processor,
            template="jingnai.html"
        ) 
    async def baizhan(self) -> Dict[str, Any]:
        """百战首领"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = data
            return_data["data"]["start"]  = format_time(data["start"])   
            return_data["data"]["end"]  = format_time(data["end"])   

        return await self._request_api(
            path="/monster/weekly",
            params= { "token": self.token},
            processor=processor,
            template="baizhan.html"
        ) 
    async def chengjiuchaxun(self, server:str, role:str, name:str) -> Dict[str, Any]:
        """成就查询"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = data

        return await self._request_api(
            path="/role/achievement",
            params= {"server": server, "role": role, "name": name, "token": self.token},
            processor=processor,
            template="chengjiu.html"
        ) 
    async def zili_menu(self) -> Dict[str, str]:
        """资历选择内容。"""
        return {
            "1": "总览",
            "2": "杂闻",
            "3": "武学",
            "4": "修为",
            "5": "装备",
            "6": "技艺",
            "7": "阅读",
            "8": "任务",
            "9": "足迹",
            "10": "战斗",
            "11": "声望",
            "12": "秘境",
            "13": "帮会",
            "14": "阵营",
            "15": "节日",
            "16": "活动",
            "17": "风雨江湖路",
            "18": "家园",
            "19": "剑侠录"
        }
    async def zili(self,server: str,name: str,selected: Dict[str, Any],) -> Dict[str, Any]:
        """资历分布"""
        if not isinstance(selected, dict) or len(selected) != 1:
            return_data = self._init_return_data()
            return_data["msg"] = "资历选项数据格式异常"
            return return_data

        selected_name = str(next(iter(selected.values())) or "").strip()
        selected_subclass = "" if selected_name == "总览" else selected_name

        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            statistics = data.get("data") or {}
            categories = statistics.get("total") or {}
            if not isinstance(categories, dict) or not categories:
                raise ValueError("接口未返回资历统计")

            # 查询总览时 total 为“大类 -> 小类 -> 统计”；指定 subclass 后，
            # JX3API 会去掉大类这一层，total 直接变成“小类 -> 统计”。
            data["subclass"] = selected_subclass
            return_data["data"] = data

        return await self._request_api(
            path="/tuilan/achievement",
            params={"server": server,"name": name,"class": 1,"subclass": selected_subclass,"ticket": self.ticket,"token": self.token,},
            processor=processor,
            template="zili.html",
        )
    async def jueshe(self,server: str, name: str, history:int) -> Dict[str, Any]:
        """角色详情"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            role_history = data.get("roleHistory") or {}
            role_names = role_history.get("roleNames") or []
            tong_names = role_history.get("TongNames") or []

            # 角色名称历史
            role_history_lines = []

            for item in role_names:
                if not isinstance(item, dict):
                    continue

                server = item.get("server") or "未知服务器"
                name = item.get("name") or "未知角色名"
                time_text = format_time(item.get("time", 0))

                role_history_lines.append(
                    f"{time_text}　{server}·{name}"
                )

            if role_history_lines:
                role_history_text = "\n".join(role_history_lines)
            else:
                role_history_text = "暂无角色历史记录"

            # 帮会历史
            tong_history_lines = []

            for item in tong_names:
                if not isinstance(item, dict):
                    continue

                server = item.get("server") or "未知服务器"
                tong_name = item.get("name") or "无帮会"
                time_text = format_time(item.get("time", 0))

                tong_history_lines.append(
                    f"{time_text}　{server}·{tong_name}"
                )

            if tong_history_lines:
                tong_history_text = "\n".join(tong_history_lines)
            else:
                tong_history_text = "暂无帮会历史记录"

            return_data["data"] = (
                f"服务器：{data.get('zoneName') or '未知'}·"
                f"{data.get('serverName') or '未知'}\n"
                f"名称：{data.get('roleName') or '未知'}\n"
                f"角色ID：{data.get('roleId') or '未知'}\n"
                f"推栏ID：{data.get('globalId') or '未知'}\n"
                f"职业：{data.get('forceName') or '未知'}·"
                f"{data.get('bodyName') or '未知'}\n"
                f"帮会：{data.get('tongName') or '无帮会'}\n"
                f"阵营：{data.get('campName') or '未知'}\n"
                f"\n"
                f"【角色历史】\n"
                f"{role_history_text}\n"
                f"\n"
                f"【帮会历史】\n"
                f"{tong_history_text}"
            )

        return await self._request_api(
            path="/role/detail",
            params= {"server": server, "name": name, "history": history, "token": self.token},
            processor=processor,
            template=""
        ) 
    async def juesheliaotian(self, server:str, name: str, limit:int, page:int) -> Dict[str, Any]:
        """角色聊天"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            chat_list = data.get("list", [])

            for item in chat_list:
                item["time"] = format_time(item.get("time", 0))

            return_data["data"] = data

        return await self._request_api(
            path="/chat/records",
            params= {"server": server,"name": name, "limit": limit, "page": page, "token": self.token},
            processor=processor,
            template="juesheliaotian.html"
        ) 
    async def shitu(self, label: int, server: str, keyword: str, limit:int) -> Dict[str, Any]:
        """师徒招募"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            items = data
            if not items:
                return_data["msg"] = "未查询到师徒招募信息"
                return return_data

            title = "收徒信息" if label == 1 else "拜师信息"
            return_data["data"] = {
                "items": items,
                "server": server,
                "keyword": keyword,
                "type_value": label,
                "title": title,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        return await self._request_api(
            path="/mentor/search",
            params= {"label": label, "server": server, "keyword": keyword, "limit": limit, "token": self.token},
            processor=processor,
            template="shitu.html"
        ) 
    async def fubengjilu(self, server:str, name: str ) -> Dict[str, Any]:
        """副本记录"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"]["list"] = data

        return await self._request_api(
            path="/raid/records",
            params= {"server": server,"name": name,"token": self.token,},
            processor=processor,
            template="fubenjilu.html"
        ) 
    

    

    
        
