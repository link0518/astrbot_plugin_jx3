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


class JX3BOXService:
    def __init__(self, config: AstrBotConfig, sqlite: AsyncSQLiteDB, cache_sqlite: Optional[AsyncSQLiteDB] = None):
        # 实例化 API Client
        self._api: APIClient = APIClient()
        # 引用插件配置文件
        self._config = config
        # 引用sqlite
        self._sql_db = sqlite
        self._cache_db = cache_sqlite or sqlite

        

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


    async def qiyugonglue(self, name: str) -> Dict[str, Any]:
        """奇遇攻略"""
        return_data = self._init_return_data()
        
        # 1. 调用基础请求
        api_url = "https://node.jx3box.com/serendipities"
        data = await self._api.get(api_url, params={"name": name}, out_key="list")
        if not data:
            return_data["msg"] = "未找到该奇遇"
            return return_data
        
        # 提取dwID
        dwID = data[0]["dwID"]
        url = f"https://node.jx3box.com/serendipity/{dwID}/achievement"
        logger.debug(f"获取ID接口地址：{url}")

        data1 = await self._api.get(url)
        url1 = f"https://cms.jx3box.com/api/cms/wiki/post/type/achievement/source/{data1['achievement_id']}"
        logger.debug(f"获取攻略接口地址：{url1}")

        # 获取奇遇攻略
        data2 = await self._api.get(url1, out_key="data")
        if not data2:
            return_data["msg"] = "获取攻略数据异常"
            return return_data
        
        # 4. 处理数据
        try:
            return_data["data"] = {}
            content = data2["post"]["content"]
            return_data["temp"] = content
        except Exception as e:
            logger.exception("处理返回数据失败")
            return_data["msg"] = "处理返回数据失败"
            return return_data

        return_data["code"] = 200

        return return_data        
