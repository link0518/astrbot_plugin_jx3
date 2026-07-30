import json
import html
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Dict, Optional

from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp

from .request import APIClient
from .sqlite import AsyncSQLiteDB
from .fun_basic import load_template,gold_to_parts,week_to_num,compare_date_str,format_time,format_remaining



ACHIEVEMENT_CHOICES = [
    (0, None, "资历总览"),
    (1, "1", "杂闻总览"),
    (2, "2", "武学总览"),
    (3, "3", "修为总览"),
    (4, "4", "装备总览"),
    (5, "5", "技艺总览"),
    (6, "6", "阅读总览"),
    (7, "7", "任务总览"),
    (8, "8", "足迹总览"),
    (9, "9", "战斗总览"),
    (10, "10", "声望总览"),
    (11, "11", "秘境总览"),
    (12, "12", "帮会总览"),
    (13, "13", "阵营总览"),
    (14, "15", "节日总览"),
    (15, "16", "活动总览"),
    (16, "17", "风雨江湖路总览"),
    (17, "40", "家园总览"),
    (18, "41", "剑侠录总览"),
]

ACHIEVEMENT_CHOICE_MAP = {index: (menu_id, title) for index, menu_id, title in ACHIEVEMENT_CHOICES}

class JX3APIService:
    def __init__(self, config: AstrBotConfig, sqlite: AsyncSQLiteDB, cache_sqlite: Optional[AsyncSQLiteDB] = None):
        # 实例化 API Client
        self._api: APIClient = APIClient()
        # 引用插件配置文件
        self._config = config
        # 引用sqlite
        self._sql_db = sqlite
        self._cache_db = cache_sqlite or sqlite

        # 获取配置中的 Token
        self.token = self._config.get("jx3api_token", "")
        if  self.token == "":
            logger.warning("获取配置token失败，请正确填写token,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置token成功。{self.token}")
        # 获取配置中的 ticket
        self.ticket = self._config.get("jx3api_ticket", "")
        if  self.ticket == "":
            logger.warning("获取配置ticket失败，请正确填写ticket,否则部分功能无法正常使用")
        else:
            logger.debug(f"获取配置ticket成功。{self.ticket}")
        

    async def close(self):
        """释放底层 APIClient 资源"""
        if self._api:
            await self._api.close()


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
            data = await self._api.get(api_url, params=params, out_key=out)
            
            if not data:
                logger.warning(f"获取接口信息失败或返回空数据: {api_url}")
            
            return data
            
        except Exception as e:
            logger.error(f"基础请求调用出错 ({api_path}): {e}")
            return None


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

        data = await self._base_request(path, params)
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


    async def richang(self, mode: str, num: int) -> Dict[str, Any]:
        """活动日历"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            if mode == "list":
                today = data.get("today") or {}
                total = data.get("total") or []

                items = [
                    {
                        "en": False,
                        "compare": "",
                        "date": "",
                        "war": "",
                        "battle": "",
                    }
                    for _ in range(week_to_num(today.get("week", "")) or 0)
                ]

                items.extend(
                    {
                        "en": True,
                        "compare": compare_date_str(item.get("date", "")),
                        "date": item.get("date", ""),
                        "war": item.get("war", ""),
                        "battle": item.get("battle", ""),
                    }
                    for item in total
                    if isinstance(item, dict)
                )

                return_data["data"]["items"] = items
                return_data["data"]["today"] = today
                return

            weekly = data.get("weekly") or {}

            return_data["data"] = (
                f"{data.get('date', '')} 星期{data.get('week', '')}\n"
                f"大战：{data.get('war', '')}\n"
                f"战场：{data.get('battle', '')}\n"
                f"阵营：{data.get('orecar', '')}\n"
                f"宗门：{data.get('school', '')}\n"
                f"驰援：{data.get('rescue', '')}\n"
                f"【宠物福缘】\n{', '.join(data.get('lucky') or [])}\n"
                f"【家园声望·加倍道具】\n{', '.join(data.get('card') or [])}\n"
                f"【武林通鉴·公共任务】\n{', '.join(weekly.get('conn') or [])}\n"
                f"【武林通鉴·团队秘境】\n{', '.join(weekly.get('raid') or [])}\n"
            )

        return await self._request_api(
            path="/active/calendar",
            params={"mode": mode, "num": num},
            processor=processor,
            template="richangyuche.html" if mode == "list" else None,
        )

    
    async def xingxiashijian(self,name: str) -> Dict[str, Any]:
        """地图活动"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            return_data["data"]["items"] = data
            return_data["data"]["name"] = name

        return await self._request_api(
            path="/active/celebs",
            params={ "name": name},
            processor=processor,
            template="xingxiashijian.html"
        )


    async def guanaishouling(self) -> Dict[str, Any]:
        """关隘首领"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            groups = [
                {
                    "server": group.get("server", ""),
                    "records": [
                        {
                            "camp_name": item.get("campName", ""),
                            "castle": item.get("castle", ""),
                            "str_status": item.get("statusText", ""),
                            "start_time": format_time(item.get("startTime")),
                            "end_time": format_time(item.get("endTime")),
                            "remaining_time": format_remaining(item.get("endTime")),
                        }
                        for item in group.get("data", [])
                        if isinstance(item, dict)
                    ],
                }
                for group in data
                if isinstance(group, dict) and group.get("data")
            ]

            groups = [group for group in groups if group["records"]]

            if not groups:
                return_data["msg"] = "未查询到关隘首领信息"
                return return_data

            return_data["data"] = {
                "groups": groups,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        return await self._request_api(
            path="/castle/status",
            params={"token": self.token},
            processor=processor,
            template="guanaishouling.html"
        )


    async def benrichitu(self) -> Dict[str, Any]:
        """本日赤兔"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            if not data or not isinstance(data, list):
                return_data["data"] = "今日赤兔 暂无数据"
                return 
            
            result_lines = ["今日赤兔"]
            for item in data:
                result_lines.extend([
                    f"时间：{item['date']}",
                    f"区服：{item['server']}",
                    f"地图：{item['mapName']}",
                ])

            return_data["data"] = "\n".join(result_lines).rstrip()
            
        return await self._request_api(
            path="/chitu/records",
            params={"token": self.token},
            processor=processor,
            template=""
        )        


    async def benzhouchitu(self) -> Dict[str, Any]:
        """本周赤兔"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            if not data or not isinstance(data, list):
                return_data["data"] = "本周赤兔 暂无数据"
                return 
            
            result_lines = ["本周赤兔"]
            for item in data:
                result_lines.extend([
                    f"时间：{item['date']}",
                    f"区服：{item['server']}",
                    f"地图：{item['mapName']}",
                ])

            return_data["data"] = "\n".join(result_lines).rstrip()
            
        return await self._request_api(
            path="/chitu/week/records",
            params={"token": self.token},
            processor=processor,
            template=""
        )  


    async def zhenyingevent(self,name: str,limit: str) -> Dict[str, Any]:
        """阵营事件"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            for item in data:
                item["seizeTime"] = format_time(item.get("seizeTime"))

            return_data["data"] = {
                "items": data,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        return await self._request_api(
            path="/fenxian/records",
            params={"token": self.token,"name": name, "limit": limit},
            processor=processor,
            template="zhenyingevent.html"
        )  
            

    async def yanhuachaxun(self, server: str, name:str ) -> Dict[str, Any]:
        """烟花记录"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:
            for item in data:
                item["time"] = format_time(item.get("time"))

            return_data["data"]["list"] = data
            
        return await self._request_api(
            path="/firework/records",
            params={"token": self.token,"name": name, "server": server},
            processor=processor,
            template="yanhuan.html"
        )  


    async def shuma(self,server:str) -> Dict[str, Any]:
        """刷马"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:    
            return_data["data"] = (
                f"【阴山大草原】\n{', '.join(data.get('阴山大草原') or [])}\n"
                f"【鲲鹏岛】\n{', '.join(data.get('鲲鹏岛') or [])}\n"
                f"【黑戈壁】\n{', '.join(data.get('黑戈壁') or [])}\n"
            )
            
        return await self._request_api(
            path="/ranch/chat",
            params={"token": self.token, "server": server},
            processor=processor,
            template=""
        )  


    async def machang(self, server: str, expired: int) -> Dict[str, Any]:
        """马场"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            data0 = data.get("data") 
            return_data["data"] = (
                f"【区服】：{data.get('server')}\n"
                f"【阴山大草原】\n{', '.join(data0.get('阴山大草原') or [])}\n"
                f"【鲲鹏岛】\n{', '.join(data0.get('鲲鹏岛') or [])}\n"
                f"【黑戈壁】\n{', '.join(data0.get('黑戈壁') or [])}\n"
                f"【龙泉府 / 进图（21:10）】\n{', '.join(data0.get('龙泉府 / 进图（21:10）') or [])}\n"
                f"\n{data.get('note')}\n"
            )
            
        return await self._request_api(
            path="/ranch/records",
            params={"token": self.token, "server": server, "expired": expired},
            processor=processor,
            template=""
        )  


    async def zhanji(self, name: str, server:str, mode:str) -> Dict[str, Any]:
        """战绩"""
        # 数据处理
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            return_data["data"] = data
            
        return await self._request_api(
            path="/arena/recent",
            params={"server": server, "name":name, "mode":mode, "token": self.token, "ticket": self.ticket},
            processor=processor,
            template="zhanji.html"
        )  


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


    async def rank_statistical(self, name: str, server: str) -> Dict[str, Any]:
        """排行榜单"""
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
            items = data.get("data", [])

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


    async def bangzhanjilu(self, server: str) -> Dict[str, Any]:
        """帮战记录"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["startTime"] = format_time(item["startTime"])
                item["durationSeconds"] = format_remaining(item["durationSeconds"])
                item["endTime"] = format_time(item["endTime"])

            return_data["data"] = {
                "items": data,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            
        return await self._request_api(
            path="/battle/records",
            params={"server": server},
            processor=processor,
            template="bangzhanjilu.html"
        ) 


    async def zhueevent(self,server: str,limit: str) -> Dict[str, Any]:
        """诛恶事件"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            for item in data:
                item["time"] = format_time(item["time"])

            return_data["data"] = {
                "items": data,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        return await self._request_api(
            path="/wicked/records",
            params={"token": self.token, "server": server, "limit": limit},
            processor=processor,
            template="zhueevent.html"
        ) 


    async def jueshemingpian(self, server: str, name: str) -> Dict[str, Any]:
        """名片缓存"""
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
            path="/card/cached",
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






    async def keju(self,subject: str, limit: int) -> Dict[str, Any]:
        """科举"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"subject": subject, "limit": limit}

        # 2. 调用基础请求
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_keju", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关题目"
            return return_data
    
        # 3. 处理返回数据
        try:
            # 格式化字符串，利用字典的 get 方法提供默认值
            result_msg = ""
            for m in data:
                result_msg += f"{m['id']}.{m['question']}\n"
                result_msg += f"答案：{m['answer']}\n\n"

            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def huajia(self,server: str, name: str, map: str) -> Dict[str, Any]:
        """花价"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "name": name,  "map": map}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_huajia", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
            return_data["data"]["server"] = server
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data

        # 加载模板
        try:
            return_data["temp"] = await load_template("huajia.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def zhuangshi(self,name: str) -> Dict[str, Any]:
        """装饰"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_zhuangshi", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
           
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
    
        # 加载模板
        try:
            return_data["temp"] = await load_template("zhuangshi.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def qiwu(self,name: str) -> Dict[str, Any]:
        """器物"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = { "name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_qiwu", "GET", params=params
        )
        if not data:
            return_data["msg"] = "未查询到相关内容"
            return return_data
    
        # 3. 处理返回数据
        try:
            return_data["data"]["data"] = data
            return_data["data"]["name"] = name
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        # 加载模板
        try:
            return_data["temp"] = await load_template("qiwu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def xinwen(self, num:int) -> Dict[str, Any]:
        """新闻资讯"""
        return_data = self._init_return_data()

        params = {"limit": num}
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_xinweng", "GET", params=params)
        
        if not data or not isinstance(data, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            # 
            result = data[0]
            return_data["status"] = result.get('id')

            result_msg = "新闻资讯推送\n"
            # 仅展示前1条，避免消息过长
            for i, item in enumerate(data[:num], 1): 
                result_msg += f"{i}. 【{item.get('type', '无类型')}】\n"
                result_msg += f"标题：{item.get('title', '未知时间')}\n"
                result_msg += f"时间：{item.get('date', '未知时间')}\n"
                result_msg += f"链接：{item.get('url', '无链接')}\n"
                
            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"

        return_data["code"] = 200    

        return return_data


    async def weihu(self, num:int) -> Dict[str, Any]:
        """维护"""
        return_data = self._init_return_data()

        params = {"limit": num}
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_weihu", "GET", params=params)
        
        if not data or not isinstance(data, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            # 
            result = data[0]
            return_data["status"] = result.get('id')

            result_msg = "维护推送\n"
            # 仅展示前1条，避免消息过长
            for i, item in enumerate(data[:num], 1): 
                result_msg += f"{i}. 【{item.get('type', '无类型')}】\n"
                result_msg += f"标题：{item.get('title', '未知时间')}\n"
                result_msg += f"时间：{item.get('date', '未知时间')}\n"
                result_msg += f"链接：{item.get('url', '无链接')}\n"
                
            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"

        return_data["code"] = 200    

        return return_data

    async def qufu(self,name: str) -> Dict[str, Any]:
        """区服信息"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"name": name}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_qufu", "GET", params=params
        )
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
    
        # 3. 处理返回数据
        try:
            # 格式化字符串，利用字典的 get 方法提供默认值
            result_msg = f"主服：{data.get('zone', '无')}-{data.get('name', '无')}\n"
            
            slave = data.get('slave', [])
            slave_msg = f"区服：{', '.join(slave)}\n"

            alias = data.get('alias', [])
            alias_msg = f"别名：{', '.join(alias)}\n"

            return_data["data"] = result_msg + slave_msg + alias_msg
            return_data["code"] = 200
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def kaifu(self, server: str) -> Dict[str, Any]:
        """开服状态查询"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server,"type": "1"}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Union[int, str]]] = await self._base_request(
            "jx3_zhuangtai", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            status = data.get("status", 0)
            lasttime = data.get("lasttime", 0)
            shuttime = data.get("shuttime", 0)
            
            lasttime_t = datetime.fromtimestamp(float(lasttime)).strftime("%Y-%m-%d %H:%M:%S")
            shuttime_t = datetime.fromtimestamp(float(shuttime)).strftime("%Y-%m-%d %H:%M:%S")
            
            if status == 1:
                status_str = f"{server}服务器已开服，快冲，快冲！\n开服时间：{lasttime_t}"
                status_bool = True
            else:
                status_str = f"{server}服务器当前维护中，等会再来吧！\n维护时间：{shuttime_t}"
                status_bool = False

            return_data["status"] = status_bool
            return_data["data"] = status_str
            
        except Exception as e:
            logger.error(f"kaifu 数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200    

        return return_data


    async def zhuangtai(self) -> Dict[str, Any]:
        """区服状态"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": "","type": "2"}
        
        data: Optional[List[Dict[str, Any]]] = await self._base_request("jx3_zhuangtai", "GET", params=params) 

        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
        # 处理返回数据
        try:
            server_wj = []
            server_dx = []
            server_sx = []

            for itme in data:
                if itme['zone'] == "无界区":
                    server_wj.append(itme)
                elif itme['zone'] == "电信区":
                    server_dx.append(itme)
                elif itme['zone'] == "双线区":
                    server_sx.append(itme)

            return_data["data"]["server_wj"] = server_wj
            return_data["data"]["server_dx"] = server_dx
            return_data["data"]["server_sx"] = server_sx
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
        # 加载模板
        try:
            return_data["temp"] = await load_template("qufuzhuangtai.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
            
        return return_data


    async def jigai(self) -> Dict[str, Any]:
        """技改记录"""
        return_data = self._init_return_data()
        
        # 提取字段可能返回列表
        data: Optional[List[Dict[str, Any]]] = await self._base_request("jx3_jigai", "GET")
        
        if not data or not isinstance(data, list):
            return_data["msg"] = "获取接口信息失败或数据格式错误"
            return return_data
        
        try:
            result_msg = "最近技改\n"
            
            for i, item in enumerate(data[:3], 1): 
                result_msg += f"{i}. {item.get('title', '无标题')}\n"
                result_msg += f"时间：{item.get('time', '未知时间')}\n"
                result_msg += f"链接：{item.get('url', '无链接')}\n\n"
                
            return_data["data"] = result_msg
            
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data


    async def xiaoyao(self) -> Dict[str, Any]:
        """小药"""
        return_data = self._init_return_data()
        
        data: Optional[List[Dict[str, Any]]] = await self._base_request("jx3_xiaoyao", "GET") 
        logger.debug(data)
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
        
        # 处理返回数据
        try:
            result = {}

            for item in data:
                k = item["kungfu"]
                color = item["color"]
                cls = item["class"]
                name = item["name"]

                if k not in result:
                    result[k] = {
                        "kungfu": k,
                        "purple": {},
                        "blue": {}
                    }

                if color == "紫":
                    result[k]["purple"][cls] = name
                else:
                    result[k]["blue"][cls] = name

            return_data["data"]["items"] = list(result.values())
            logger.debug(return_data["data"])

        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"

        # 加载模板
        try:
            return_data["temp"] = await load_template("xiaoyao.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
            
        return return_data


    async def zhenyan(self, name: str) -> Dict[str, Any]:
        """阵眼"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"name": name, "ticket": self.ticket, "token": self.token}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_zhenyan", "GET", params=params
        )

        if not data or not isinstance(data, dict):
            return_data["msg"] = "未查询到该心法阵眼信息"
            return return_data

        # 3. 处理返回数据
        try:
            items = data.get("data", [])
            if not isinstance(items, list) or not items:
                return_data["msg"] = "未查询到该心法阵眼信息"
                return return_data

            result_msg = f"{data.get('name', name)}-{data.get('skillName', '')}\n"
            for item in items:
                if not isinstance(item, dict):
                    continue
                result_msg += f"{item.get('name', '')}：{item.get('desc', '')}\n"

            return_data["data"] = result_msg.rstrip()
        except Exception as e:
            logger.error(f"处理阵眼数据失败: {e}")
            return_data["msg"] = "处理阵眼数据失败"
            return return_data

        return_data["code"] = 200

        return return_data


    async def qixue(self, name: str) -> Dict[str, Any]:
        """奇穴"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"name": name, "ticket": self.ticket, "token": self.token}

        # 2. 调用基础请求
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_qixue", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到该心法奇穴信息"
            return return_data

        # 3. 处理返回数据
        try:
            level_titles = {
                1: "主奇穴",
                2: "第一重",
                3: "第二重",
                4: "第三重",
                5: "第四重",
                6: "第五重",
                7: "第六重",
                8: "混池",
            }

            groups = []
            for group in data:
                if not isinstance(group, dict):
                    continue

                level = group.get("level")
                try:
                    level_key = int(level)
                except (TypeError, ValueError):
                    level_key = 0

                items = group.get("data", [])
                if not isinstance(items, list) or not items:
                    continue

                parsed_items = []
                for item in items:
                    if not isinstance(item, dict):
                        continue

                    class_value = item.get("class")
                    is_active = class_value == 1 or str(class_value) == "1"
                    parsed_items.append({
                        "name": item.get("name", ""),
                        "icon": item.get("icon", ""),
                        "desc": item.get("desc", ""),
                        "class_text": "主动" if is_active else "被动",
                        "interval": item.get("interval", "") if is_active else "",
                    })

                if parsed_items:
                    groups.append({
                        "level": level_key,
                        "title": level_titles.get(level_key, f"第{level_key}组"),
                        "talents": parsed_items,
                    })

            if not groups:
                return_data["msg"] = "未查询到该心法奇穴信息"
                return return_data

            groups.sort(key=lambda item: item["level"])
            return_data["data"] = {
                "name": name,
                "groups": groups,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"处理奇穴数据失败: {e}")
            return_data["msg"] = "处理奇穴数据失败"
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("qixue.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200
        return return_data


    async def jineng(self, name: str) -> Dict[str, Any]:
        """技能"""
        return_data = self._init_return_data()

        params = {"name": name, "ticket": self.ticket, "token": self.token}

        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_jineng", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到该心法技能信息"
            return return_data

        try:
            groups = []
            for group in data:
                if not isinstance(group, dict):
                    continue

                skills = group.get("data", [])
                if not isinstance(skills, list) or not skills:
                    continue

                parsed_skills = []
                for skill in skills:
                    if not isinstance(skill, dict):
                        continue

                    parsed_skills.append({
                        "name": skill.get("name", ""),
                        "icon": skill.get("icon", ""),
                        "desc": skill.get("desc", ""),
                        "interval": skill.get("interval", ""),
                        "distance": skill.get("distance", ""),
                        "release_type": skill.get("releaseType", ""),
                        "weapon": skill.get("weapon", ""),
                    })

                if parsed_skills:
                    groups.append({
                        "title": group.get("class", "其他技能"),
                        "skills": parsed_skills,
                    })

            if not groups:
                return_data["msg"] = "未查询到该心法技能信息"
                return return_data

            return_data["data"] = {
                "name": name,
                "groups": groups,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"处理技能数据失败: {e}")
            return_data["msg"] = "处理技能数据失败"
            return return_data

        try:
            return_data["temp"] = await load_template("jineng.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200

        return return_data


    async def zilipaixing(self, school: str, server: str) -> Dict[str, Any]:
        """资历排行"""
        return_data = self._init_return_data()

        params = {
            "server": server,
            "school": school,
            "ticket": self.ticket,
            "token": self.token,
        }

        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_zilipaixing", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到资历排行信息"
            return return_data

        try:
            return_data["data"] = {
                "items": data,
                "school": school,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"处理资历排行数据失败: {e}")
            return_data["msg"] = "处理资历排行数据失败"
            return return_data

        try:
            return_data["temp"] = await load_template("zilipaixing.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200

        return return_data




    async def shaohua(self) -> Dict[str, Any]:
        """骚话"""
        return_data = self._init_return_data()
        
        # 因为没有参数，所以 params=None
        data: Optional[Dict[str, Any]] = await self._base_request("jx3_shaohua", "GET") 
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        text = data.get("text")
        if text:
            return_data["data"] = text
        else:
            return_data["msg"] = "接口未返回文本"
            return return_data

        return_data["code"] = 200  

        return return_data


    async def jiemi(self) -> Dict[str, Any]:
        """解密"""
        return_data = self._init_return_data()

        params = {"token": self.token}

        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jiemi", "GET", params=params
        )

        if not data or not isinstance(data, dict):
            return_data["msg"] = "未查询到解密信息"
            return return_data

        try:
            curr = data.get("curr", {})
            next_data = data.get("next", {})
            if not isinstance(curr, dict):
                curr = {}
            if not isinstance(next_data, dict):
                next_data = {}

            return_data["data"] = "\n".join([
                "解密",
                f"当前时间：{data.get('time', '')}",
                f"当前节点：{curr.get('node', '')}",
                f"当前结果：{curr.get('data', '')}",
                f"下轮节点：{next_data.get('node', '')}",
                f"下轮结果：{next_data.get('data', '')}",
                f"剩余时间：{data.get('cdtn', '')}",
            ])
        except Exception as e:
            logger.error(f"处理解密数据失败: {e}")
            return_data["msg"] = "处理解密数据失败"
            return return_data

        return_data["code"] = 200

        return return_data






    async def baizhan(self) -> Dict[str, Any]:
        """百战首领"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = { "token": self.token}
        
        data: Optional[Dict[str, Any]] = await self._base_request("jx3_baizhan", "GET", params=params) 

        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
        # 处理返回数据

        try:
            return_data["data"] = data
            return_data["data"]["start"]  = datetime.fromtimestamp(float(data["start"])).strftime("%Y-%m-%d %H:%M:%S")
            return_data["data"]["end"]  = datetime.fromtimestamp(float(data["end"])).strftime("%Y-%m-%d %H:%M:%S")

        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
        # 加载模板
        try:
            return_data["temp"] = await load_template("baizhan.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
            
        return return_data


    async def fuyaojjiutian(self, server: str) -> Dict[str, Any]:
        """扶摇九天"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[list[Dict[str, Any]]] = await self._base_request(
            "jx3_fuyaojiutian", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            data_new =  data[0]
            data_time =  datetime.fromtimestamp(data_new['time']).strftime('%Y-%m-%d %H:%M:%S')
            result_msg = f"{server}\n"
            if data_new["status"] == 0:
                result_msg += f"本轮扶摇九天尚未开启\n"
            if data_new["status"] == 1:
                result_msg += f"本轮扶摇九天正在进行\n"
            if data_new["status"] == 2:
                result_msg += f"本轮扶摇九天已经结束\n"
            result_msg += f"开启时间：{data_time}\n"
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data    
        
        return_data["code"] = 200
        
        return return_data












    










    async def tongzhanyy(self, server: str) -> Dict[str, Any]:
        """统战歪歪"""
        return_data = self._init_return_data()

        params = {
            "server": server,
            "token": self.token,
        }

        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_tongzhanyy", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到统战歪歪信息"
            return return_data

        try:
            lines = ["统战歪歪"]
            has_channel = False

            for group in data:
                if not isinstance(group, dict):
                    continue

                group_server = group.get("server", "")
                channels = group.get("data", [])
                if not isinstance(channels, list) or not channels:
                    continue

                if len(lines) > 1:
                    lines.append("")
                lines.append(f"服务器：{group_server}")

                for item in channels:
                    if not isinstance(item, dict):
                        continue

                    has_channel = True
                    short_id = item.get("esid") or item.get("asid", "")
                    lines.extend([
                        f"阵营：{item.get('campName', '')}",
                        f"频道ID：{item.get('sid', '')}",
                        f"短位ID：{short_id}",
                        f"在线人数：{item.get('users', '')}",
                        f"频道名：{item.get('snick', '')}",
                        "",
                    ])

            if not has_channel:
                return_data["msg"] = "未查询到统战歪歪信息"
                return return_data

            return_data["data"] = "\n".join(lines).rstrip()
        except Exception as e:
            logger.error(f"处理统战歪歪数据失败: {e}")
            return_data["msg"] = "处理统战歪歪数据失败"
            return return_data

        return_data["code"] = 200

        return return_data








    async def pianzhi(self, uid: str) -> Dict[str, Any]:
        """骗子查询"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"uid": uid, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_pianzhi", "GET", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据
        try:
            records = data["records"]

            if not records:
                result_msg = "未找到该用户行骗记录，很棒！继续保持！"
            else:
                result_msg = ""

                for record in records:
                    result_msg += f"区服：{record['server']}  标签：{record['tieba']}\n\n"

                    for item in record["data"]:
                        result_msg += f"标题：{item['title']}\n"
                        result_msg += f"地址：{item['url']}\n"
                        result_msg += f"ID：{item['tid']}\n"
                        result_msg += f"内容：{item['text']}\n"
                        result_msg += (
                            f"时间：{datetime.fromtimestamp(item['time']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        )

                    result_msg += "\n\n"
            return_data["data"] = result_msg
        except Exception as e:
            logger.error(f"处理返回数据失败: {e}")
            return_data["msg"] = "处理返回数据失败"
            return return_data
            
        return_data["code"] = 200
        
        return return_data


























    async def tuanduizhaomu(self, server: str, keyword: str) -> Dict[str, Any]:
        """团队招募"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"server": server, "keyword": keyword, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_tuanduizhaomu", "GET", params=params
        )

        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data   
        
        # 3. 处理返回数据 
        try: 
            for item in data["data"]:
                item["createTime"] = datetime.fromtimestamp(item["createTime"]).strftime("%Y-%m-%d %H:%M:%S")
                item["number"] = f"{item['number']}/{item['maxNumber']}"
                return_data["data"]["list"] = data["data"]
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错" 
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("tuanduizhaomu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data


    async def shitu(self, type_value: int, keyword: str, server: str) -> Dict[str, Any]:
        """师徒招募"""
        return_data = self._init_return_data()
        
        if type_value not in {1, 2}:
            return_data["msg"] = "师徒查询类型错误"
            return return_data

        # 1. 构造请求参数
        params = {"type": type_value, "server": server, "keyword": keyword, "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_shitu", "GET", params=params
        )

        if not data or not isinstance(data, dict):
            return_data["msg"] = "未查询到师徒招募信息"
            return return_data
        
        # 3. 处理返回数据 
        try:
            items = data.get("data", [])
            if not items:
                return_data["msg"] = "未查询到师徒招募信息"
                return return_data

            title = "收徒信息" if type_value == 1 else "拜师信息"
            return_data["data"] = {
                "items": items,
                "server": data.get("server", server),
                "keyword": keyword,
                "type_value": type_value,
                "title": title,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错" 
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("shitu.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data
        
        return_data["code"] = 200
        
        return return_data





    async def _load_achievement_cache(self, key: str) -> tuple[Optional[Any], bool]:
        """读取资历基础数据缓存，返回数据和是否已过期"""
        try:
            row = await self._cache_db.select_one("achievement_cache", "key=?", (key,))
        except Exception as e:
            logger.error(f"读取资历缓存失败: {e}")
            return None, True

        if not row:
            return None, True

        try:
            payload = json.loads(row.get("content", "{}"))
            updated_at = datetime.strptime(row.get("updated_at", ""), "%Y-%m-%d %H:%M:%S")
            expired = datetime.now() - updated_at > timedelta(days=30)
            return payload, expired
        except Exception as e:
            logger.error(f"解析资历缓存失败: {e}")
            return None, True


    async def _save_achievement_cache(self, key: str, payload: Any):
        """写入资历基础数据缓存"""
        try:
            await self._cache_db.execute(
                """
                INSERT INTO achievement_cache (key, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    updated_at=excluded.updated_at
                """,
                (
                    key,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        except Exception as e:
            logger.error(f"写入资历缓存失败: {e}")


    async def _get_achievement_base_data(self, cache_key: str, config_key: str) -> Optional[Dict[str, Any]]:
        """获取资历菜单或点数数据，优先使用未过期缓存"""
        cached, expired = await self._load_achievement_cache(cache_key)
        if cached and not expired:
            return cached

        data: Optional[Dict[str, Any]] = await self._base_request(config_key, "GET")
        if data and isinstance(data, dict):
            await self._save_achievement_cache(cache_key, data)
            return data

        if cached:
            logger.warning(f"资历基础数据接口失败，使用旧缓存: {cache_key}")
            return cached

        return None


    async def _get_trade_item_groups(self) -> Optional[List[Dict[str, Any]]]:
        """获取交易行物品库，优先使用未过期缓存"""
        cache_key = "trade_item_groups"
        cached, expired = await self._load_achievement_cache(cache_key)
        if isinstance(cached, list) and not expired:
            return cached

        data = await self._base_request("jx3box_trade_items", "GET")
        if isinstance(data, list) and data:
            await self._save_achievement_cache(cache_key, data)
            return data

        if isinstance(cached, list) and cached:
            logger.warning("交易行物品库接口失败，使用旧缓存")
            return cached

        return None


    def _flatten_trade_items(self, groups: List[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """从交易行物品分组中提取可查询物品"""
        items = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            for item in group.get("items", []) or []:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                label = item.get("label")
                if not item_id or not label:
                    continue
                items.append(
                    {
                        "item_id": str(item_id),
                        "label": str(label),
                        "icon": str(item.get("icon") or ""),
                    }
                )
        return items


    def _match_trade_items(self, items: list[Dict[str, Any]], keyword: str, limit: int = 50) -> list[Dict[str, Any]]:
        """按物品名模糊匹配交易行物品"""
        keyword = (keyword or "").strip()
        if not keyword:
            return []

        matched = []
        seen = set()
        for item in items:
            label = item.get("label", "")
            item_id = item.get("item_id", "")
            if keyword not in label or item_id in seen:
                continue
            seen.add(item_id)
            if label == keyword:
                rank = 0
            elif label.startswith(keyword):
                rank = 1
            else:
                rank = 2
            matched.append((rank, len(label), label, item))

        matched.sort(key=lambda row: (row[0], row[1], row[2]))
        return [row[3] for row in matched[:limit]]


    def _flatten_achievement_ids(self, values: Any) -> list[int]:
        """展开菜单中的单个资历 ID 和数组资历 ID"""
        result = []

        if isinstance(values, list):
            for item in values:
                result.extend(self._flatten_achievement_ids(item))
            return result

        try:
            result.append(int(values))
        except (TypeError, ValueError):
            pass

        return result


    def _category_achievement_ids(self, category: Dict[str, Any]) -> list[int]:
        """提取分类及其子分类包含的资历 ID"""
        ids = self._flatten_achievement_ids(category.get("achievements", []))
        for child in category.get("children", []) or []:
            if isinstance(child, dict):
                ids.extend(self._flatten_achievement_ids(child.get("achievements", [])))
        return ids


    def _build_achievement_progress(
        self,
        name: str,
        achievement_ids: list[int],
        point_map: Dict[str, Any],
        completed_ids: set[int],
    ) -> Dict[str, Any]:
        """按资历点数计算完成进度"""
        unique_ids = set(achievement_ids)
        total_points = 0
        completed_points = 0
        completed_count = 0

        for achievement_id in unique_ids:
            try:
                point = int(point_map.get(str(achievement_id), 0) or 0)
            except (TypeError, ValueError):
                point = 0

            total_points += point
            if achievement_id in completed_ids:
                completed_count += 1
                completed_points += point

        percent = round(completed_points / total_points * 100, 2) if total_points else 0

        return {
            "name": name,
            "total_points": total_points,
            "completed_points": completed_points,
            "percent": percent,
            "percent_text": f"{percent:.2f}%",
            "achievement_count": len(unique_ids),
            "completed_count": completed_count,
        }


    async def zili(self, name: str, server: str, choice: int) -> Dict[str, Any]:
        """角色资历"""
        return_data = self._init_return_data()

        if choice not in ACHIEVEMENT_CHOICE_MAP:
            return_data["msg"] = "无效序号，结束会话"
            return return_data

        role_params = {"server": server, "name": name, "token": self.token}
        role_data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jueshexinxi", "GET", params=role_params
        )
        if not role_data or not isinstance(role_data, dict):
            return_data["msg"] = "未查询到角色"
            return return_data

        global_id = role_data.get("globalId")
        if not global_id:
            return_data["msg"] = "无法获取角色全区 ID"
            return return_data

        achievement_data = await self._api.get(
            "https://next2.jx3box.com/api/next2/user-achievements",
            params={"jx3id": global_id},
            out_key="data",
        )
        if not achievement_data or not isinstance(achievement_data, dict):
            return_data["msg"] = "未查询到资历数据"
            return return_data

        completed_ids = set()
        achievements = achievement_data.get("achievements") or ""
        if isinstance(achievements, str):
            for item in achievements.split(","):
                try:
                    completed_ids.add(int(item.strip()))
                except ValueError:
                    continue
        elif isinstance(achievements, list):
            completed_ids = set(self._flatten_achievement_ids(achievements))

        menu_payload = await self._get_achievement_base_data(
            "achievement_menus",
            "jx3box_achievement_menus",
        )
        point_payload = await self._get_achievement_base_data(
            "achievement_points",
            "jx3box_achievement_points",
        )
        if not menu_payload or not point_payload:
            return_data["msg"] = "基础资历数据获取失败"
            return return_data

        menus = menu_payload.get("menus", {})
        points = point_payload.get("points", {})
        if not isinstance(menus, dict) or not isinstance(points, dict):
            return_data["msg"] = "基础资历数据格式异常"
            return return_data

        selected_menu_id, selected_title = ACHIEVEMENT_CHOICE_MAP[choice]
        items = []

        if choice == 0:
            total_ids = []
            for _, menu_id, title in ACHIEVEMENT_CHOICES[1:]:
                category = menus.get(str(menu_id), {})
                if not isinstance(category, dict):
                    continue
                category_ids = self._category_achievement_ids(category)
                total_ids.extend(category_ids)
                items.append(
                    self._build_achievement_progress(title, category_ids, points, completed_ids)
                )
            summary = self._build_achievement_progress(selected_title, total_ids, points, completed_ids)
        else:
            category = menus.get(str(selected_menu_id), {})
            if not isinstance(category, dict) or not category:
                return_data["msg"] = "未找到该资历分类"
                return return_data

            category_ids = self._category_achievement_ids(category)
            summary = self._build_achievement_progress(selected_title, category_ids, points, completed_ids)
            for child in category.get("children", []) or []:
                if not isinstance(child, dict):
                    continue
                child_ids = self._flatten_achievement_ids(child.get("achievements", []))
                items.append(
                    self._build_achievement_progress(child.get("name", "未命名"), child_ids, points, completed_ids)
                )

        try:
            return_data["temp"] = await load_template("zili.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["data"] = {
            "title": selected_title,
            "summary": summary,
            "items": items,
            "role_name": role_data.get("roleName", name),
            "server": role_data.get("serverName", server),
            "zone": role_data.get("zoneName", ""),
            "force_name": role_data.get("forceName", "无"),
            "camp_name": role_data.get("campName", "无"),
            "tong_name": role_data.get("tongName", "无"),
            "updated_at": achievement_data.get("updated_at", ""),
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return_data["code"] = 200

        return return_data


    async def jueshe(self,name: str, server: str) -> Dict[str, Any]:
        """角色"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "name": name, "token": self.token}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jueshexinxi", "GET", params=params
        )
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
    
        # 3. 处理返回数据
        try:
            # 格式化字符串，利用字典的 get 方法提供默认值
            result_msg = (
                f"服务器：{data.get('zoneName', '无')}·{data.get('serverName', '无')}\n"
                f"名称：{data.get('roleName', '无')}\n"
                f"角色ID：{data.get('roleId', '无')}\n"
                f"全区ID：{data.get('globalId', '无')}\n"
                f"职业：{data.get('forceName', '无')}·{data.get('bodyName', '无')}\n"
                f"帮会：{data.get('tongName', '无')}\n"
                f"阵营：{data.get('campName', '无')}\n"
            )

            return_data["data"] = result_msg
            return_data["code"] = 200
        except Exception as e:
            logger.error(f"数据处理时出错: {e}")
            return_data["msg"] = "处理接口返回信息时出错"
            return return_data
        
        return_data["code"] = 200

        return return_data





    async def jingnai(self, name: str, server: str) -> Dict[str, Any]:
        """百战精耐"""
        return_data = self._init_return_data()

        # 1. 构造请求参数
        params = {"server": server, "name": name, "token": self.token}

        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3_jingnai", "GET", params=params
        )

        if not data or not isinstance(data, dict):
            return_data["msg"] = "未查询到角色精耐信息"
            return return_data

        # 3. 处理返回数据
        try:
            items = data.get("skill_list", [])
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

                color = item.get("skill_color")
                try:
                    color_key = int(color)
                except (TypeError, ValueError):
                    color_key = None
                item["skill_color_text"] = color_map.get(color_key, str(color) if color is not None else "")

            update_time = data.get("update_time")
            if update_time:
                try:
                    update_time = datetime.fromtimestamp(int(update_time)).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError):
                    update_time = str(update_time)
            else:
                update_time = ""

            return_data["data"] = {
                "server": data.get("server", server),
                "role_name": data.get("role_name", name),
                "skill_energy": data.get("skill_energy", ""),
                "skill_stamina": data.get("skill_stamina", ""),
                "skill_count": data.get("skill_count", len(items)),
                "items": items,
                "update_time": update_time
            }
        except Exception as e:
            logger.error(f"处理精耐数据失败: {e}")
            return_data["msg"] = "处理精耐数据失败"
            return return_data

        # 4. 加载模板
        try:
            return_data["temp"] = await load_template("jingnai.html")
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return_data["code"] = 200

        return return_data









    






    async def jiaoyihang(self, name: str , server: str) -> Dict[str, Any]:
        """区服交易行"""
        return_data = self._init_return_data()

        item_groups = await self._get_trade_item_groups()
        if not item_groups:
            return_data["msg"] = "交易行基础物品数据获取失败"
            return return_data

        trade_items = self._flatten_trade_items(item_groups)
        matched_items = self._match_trade_items(trade_items, name, 50)
        if not matched_items:
            return_data["msg"] = "未找到匹配的交易行物品"
            return return_data

        item_map = {item["item_id"]: item for item in matched_items}
        params = {
            "item_ids": list(item_map.keys()),
            "server": server,
            "aggregate_type": "hourly",
        }
        price_data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_jiaoyihang", "POST", params=params, out_key=""
        )

        if not price_data or not isinstance(price_data, list):
            return_data["msg"] = "未查询到交易行价格数据"
            return return_data

        try:
            result = []
            for price_item in price_data:
                if not isinstance(price_item, dict):
                    continue

                item_id = str(price_item.get("item_id") or "")
                base_item = item_map.get(item_id)
                if not base_item:
                    continue

                timestamp = price_item.get("timestamp")
                try:
                    created = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError):
                    created = ""

                result.append(
                    {
                        "item_id": item_id,
                        "name": base_item.get("label", ""),
                        "icon": f"https://icon.jx3box.com/icon/{base_item.get('icon', '')}.png",
                        "server": price_item.get("server", server),
                        "price": price_item.get("price", 0),
                        "price_parts": gold_to_parts(price_item.get("price", 0)),
                        "sample": price_item.get("sample", 0),
                        "created": created,
                    }
                )

            if not result:
                return_data["msg"] = "未查询到交易行价格数据"
                return return_data

            return_data["data"] = {
                "search_name": name,
                "server": server,
                "matched_count": len(matched_items),
                "result_count": len(result),
                "list": result,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            logger.error(f"处理交易行数据失败: {e}")
            return_data["msg"] = "处理交易行数据失败"
            return return_data

        # 5. 模板渲染
        try:
            return_data["temp"] = await load_template("jiaoyihang.html")
            return_data["code"] = 200
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return return_data


    async def tiebawujia(self, name: str, limit: int = 5, server: str = "") -> Dict[str, Any]:
        """贴吧物价"""
        return_data = self._init_return_data()

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return_data["msg"] = "记录数量必须是数字"
            return return_data

        if limit < 1 or limit > 50:
            return_data["msg"] = "贴吧物价记录数量必须在 1-50 之间"
            return return_data

        params = {
            "server": server,
            "name": name,
            "limit": limit,
            "token": self.token,
        }

        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_tiebawujia", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到贴吧物价记录"
            return return_data

        try:
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
        except Exception as e:
            logger.error(f"处理贴吧物价数据失败: {e}")
            return_data["msg"] = "处理贴吧物价数据失败"
            return return_data

        return_data["code"] = 200

        return return_data


    async def diaoluo(self, name: str, limit: int = 20, server: str = "") -> Dict[str, Any]:
        """物品掉落记录"""
        return_data = self._init_return_data()

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return_data["msg"] = "数量必须是数字"
            return return_data

        if limit < 1 or limit > 100:
            return_data["msg"] = "掉落记录数量需在 1-100 之间"
            return return_data

        # 1. 构造请求参数
        params = {"server": server, "name": name, "limit": limit, "token": self.token}

        # 2. 调用基础请求
        data: Optional[List[Dict[str, Any]]] = await self._base_request(
            "jx3_diaoluo", "GET", params=params
        )

        if not data or not isinstance(data, list):
            return_data["msg"] = "未查询到掉落记录"
            return return_data

        # 3. 处理返回数据
        try:
            for item in data:
                if not isinstance(item, dict):
                    continue

                drop_time = item.get("time")
                if drop_time:
                    try:
                        item["time"] = datetime.fromtimestamp(int(drop_time)).strftime("%Y-%m-%d %H:%M:%S")
                    except (TypeError, ValueError, OSError):
                        item["time"] = str(drop_time)
                else:
                    item["time"] = ""

            return_data["data"] = {
                "items": data,
                "name": name,
                "limit": limit,
                "server": server,
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"处理掉落数据失败: {e}")
            return_data["msg"] = "处理掉落数据失败"
            return return_data

        # 4. 模板渲染
        try:
            return_data["temp"] = await load_template("diaoluo.html")
            return_data["code"] = 200
        except FileNotFoundError as e:
            logger.error(f"加载模板失败: {e}")
            return_data["msg"] = "系统错误：模板文件不存在"
            return return_data

        return return_data
    

    async def bagua(self, type: str) -> Dict[str, Any]:
        """八卦"""
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"class": type, "limit": "5", "token": self.token}
        
        # 2. 调用基础请求
        data: Optional[list[Dict[str, Any]]] = await self._base_request(
            "jx3_bagua", "GET", params=params
        )
        
        # 3. 处理返回数据
        try:
            if not data:
                result_msg = f"未找到相关 {type} 记录。\n"
                result_msg += f"可选范围：818 616 鬼网三 鬼网3 树洞 记录 教程 街拍 故事 避雷 吐槽 提问"
            else:
                result_msg = f"类型：【{type}】\n\n"

                for item in data:
                    result_msg += f"{item['title']}\n"
                    result_msg += f"分区：{item['zone']}  服务器：{item['server']}\n"
                    result_msg += f"所属吧：{item['name']}\n"
                    result_msg += f"链接：https://tieba.baidu.com/p/{item['url']}\n"
                    result_msg += f"日期：{item['date']}\n\n"
            return_data["data"] = result_msg
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data    

        return_data["code"] = 200
        
        return return_data



    

    async def hong1(self, name: str) -> Dict[str, Any]:
        """宏 心法"""
        return_data = self._init_return_data()
        
        # 数据库查询数据
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )

        if result is None:
            return_data["msg"] = "未找到该心法"
            return return_data

        kungfu = result.get("name", None)
        if kungfu is None:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        logger.debug(f"查询到数据：{kungfu}")

        # 1. 构造请求参数
        params = {"subtype": kungfu}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3box_hong", "GET", params=params
        )
        logger.debug(data)
        if not data:
            return_data["msg"] = "未找到该心法一键宏"
            return return_data
        
        # 提取ID
        pid_list = [0]
        msg = "按照热度排列\n"
        n = 1
        try:
            for m in data.get('list',[]):
                msg += f"{n}、{m['author']}\t{m['post_title']}\n"
                pid_list.append(m["ID"])
                n += 1
            
            return_data["msg"] = msg
            return_data["data"]["list"] = pid_list
            return_data["data"]["num"] = n

        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def hong2(self, pid: str) -> Dict[str, Any]:
        """宏 心法"""
        return_data = self._init_return_data()
        
        # 发起请求
        url = f"https://cms.jx3box.com/api/cms/post/{pid}"
        logger.debug(f"获取宏接口地址：{url}")

        data = await self._api.get(url, out_key="data")
        # 验证数据
        if not data:
            return_data["msg"] = "获取宏数据异常"
            return return_data
        
        # 4. 处理数据
        try:
            return_data["temp"] = data["post_content"]
            msg = ""
            for m in data["post_meta"]["data"]:
                msg += f"【宏名称】\n{m['name']}\n"
                msg += f"【使用说明】\n{m['desc']}\n"
                msg += f"【宏脚本】\n{m['macro']}\n\n"

            return_data["data"] = msg
            
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data
        
        return_data["code"] = 200

        return return_data
    

    async def peizhuang(self, name: str, tags: str) -> Dict[str, Any]:
        """配装"""
        return_data = self._init_return_data()
        
        # 数据库查询数据
        result = await self._sql_db.select_one(
                "kungfu",
                "name=? OR name1=? OR name2=? OR name3=? OR name4=? OR name5=?",
                (name, name, name, name, name, name)
            )
        logger.debug(result)
        if result is None:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        mount = result.get("pzid", None)
        if not mount:
            return_data["msg"] = "未找到该心法"
            return return_data
        
        logger.debug(f"查询到数据：{mount}")

        # 1. 构造请求参数
        params = {"mount": mount, "tags": tags}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "jx3box_peizhuang", "GET", params=params
        )
        logger.debug(data)
        # 验证数据
        if not data:
            return_data["msg"] = "配装数据获取异常"
            return return_data
        
        # 3. 处理返回数据
        try:
            result_msg = f"{name}--配装\n"        
            for item in data["list"]:
                result_msg += f"【{item['zlp']}】--{item['title']}\n"
                result_msg += f"链接：https://www.jx3box.com/pz/view/{item['id']}\n\n"

            return_data["data"] = result_msg

        except Exception as e:
            logger.exception("处理返回数据失败:",e)
            return_data["msg"] = "处理返回数据失败"
            return return_data    

        return_data["code"] = 200
        
        return return_data
    
        
