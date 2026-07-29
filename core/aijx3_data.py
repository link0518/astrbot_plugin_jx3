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


class AIJX3Service:
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

            base_url = "https://www.jianxiachaguan.cn"
            api_url = base_url + api_path
            data = await self._api.post(api_url, data=params, out_key=out)
            
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


    async def shapan(self, server: str ) -> Dict[str, Any]:
        """区服沙盘"""
        async def processor(data: Any, return_data: Dict[str, Any]) -> None:   
            pic_url = data.get("picUrl")
            if pic_url:
                return_data["data"] = pic_url
            else:
                return_data["msg"] = "接口未返回图片URL"
                return return_data
            
        return await self._request_api(
            path="/api2/aijx3-jxcg/game/get-sand-table-img",
            params={"serverName": server},
            processor=processor,
            template=""
        ) 
        return_data = self._init_return_data()
        
        # 1. 构造请求参数
        params = {"serverName": server}
        
        # 2. 调用基础请求
        data: Optional[Dict[str, Any]] = await self._base_request(
            "aijx3_shapan", "POST", params=params
        )
        
        if not data:
            return_data["msg"] = "获取接口信息失败"
            return return_data
            
        # 3. 处理返回数据 (直接提取图片 URL)
        pic_url = data.get("picUrl")
        if pic_url:
            return_data["data"] = pic_url
        else:
            return_data["msg"] = "接口未返回图片URL"
            return return_data
        
        return_data["code"] = 200    

        return return_data   
        
