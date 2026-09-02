import inspect
from pathlib import Path
from typing import cast

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.api import AstrBotConfig

from .core.sqlite import AsyncSQLiteDB
from .core.jx3api_data import JX3APIService
from .core.jx3box_data import JX3BOXService
from .core.event_push import EventPushService
from .core.bilei_data import BiLeidata
from .core.message import MessageBuilder
from .core.fun_basic import load_as_base64

@register("astrbot_plugin_jx3", 
          "fxdyz", 
          "聚合剑网三游戏数据，提供查询、图片渲染、本地避雷和实时事件推送。",
          "3.3.1",
          "https://github.com/qsc20001102/astrbot_plugin_jx3"
)
class Jx3ApiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 获取插件配置
        self.conf = config

        # 指令前缀
        self.prefix = self.conf.get("prefix",{})
        if self.prefix.get("enable"):
            logger.info(f"已启用指令前缀功能，前缀为：{self.prefix.get('text')}")
        else:
            logger.info(f"未启用指令前缀功能。")

        # 默认服务器
        self.server = self.conf.get("server","梦江南")
        logger.info(f"配置加载默认服务器：{self.server}")

        # 获取数据文件路径
        self.get_data_path()
        # 加载图片base64编码
        self.load_local_base64()
        # 构造所有类
        self.create_all()


        # 声明指令集
        self.command_map = {}

        logger.info("jx3api插件初始化完成")


    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""     
        try:
            # 数据库初始化
            await self.init_bilei_data()
            await self.init_achievement_cache_data()

            # 连接插件数据
            await self.plugin_sql_db.connect()

            # 开启实时事件通道
            await self.event_push.initialize()

        except Exception as e:
            if self.event_push is not None:
                await self.event_push.stop()
            logger.exception("功能模块初始化失败")
            raise

        # 指令集
        self.ini_command_map()

        logger.info("jx3api 异步插件初始化完成")


    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        
        if self.event_push:
            await self.event_push.stop()

        if self.jx3api:
            await self.jx3api.close()

        if self.jx3box:
            await self.jx3box.close()

        if self.local_sql_db:
            await self.local_sql_db.close()
            
        if self.plugin_sql_db:
            await self.plugin_sql_db.close()
            
        logger.info("jx3api插件已卸载/停用")


    def get_data_path(self):
        """获取数据文件路径"""
        # 本地数据存储路径
        self.local_data_dir = StarTools.get_data_dir("astrbot_plugin_jx3")
        # 插件数据存储路径
        self.plugin_data_dir = Path(__file__).parent / "data"
        self.plugin_temp_dir = Path(__file__).parent /"templates"

        # SQLite本地路径
        self.local_data_path = self.local_data_dir / "local_data.db"
        # SQLite插件路径
        self.plugin_data_path = self.plugin_data_dir /"plugin_data.db"

        # 图片文件路径
        self.plugin_temp_img = self.plugin_temp_dir / "img"
        self.plugin_temp_sand = self.plugin_temp_img / "sand"
        self.plugin_temp_sect = self.plugin_temp_dir / "sect"
        self.plugin_temp_serendipity = self.plugin_temp_dir / "serendipity"

        # 数据路径打印
        logger.debug(f"本地数据路径: {self.local_data_path}")
        logger.debug(f"插件数据路径: {self.plugin_data_path}")
        logger.debug(f"图片文件路径: {self.plugin_temp_img}")
        logger.debug(f"沙盘图片文件路径: {self.plugin_temp_sand}")
        logger.debug(f"图片文件路径: {self.plugin_temp_sect}")
        logger.debug(f"图片文件路径: {self.plugin_temp_serendipity}")


    def load_local_base64(self):
        """加载图片文件的base64编码"""
        img = load_as_base64(str(self.plugin_temp_img))
        sand = load_as_base64(str(self.plugin_temp_sand))
        sect = load_as_base64(str(self.plugin_temp_sect))
        serendipity = load_as_base64(str(self.plugin_temp_serendipity))
        self.icons =  {
            "img": img,
            "sand": sand,
            "sect": sect,
            "serendipity": serendipity
        }        
        logger.debug(f"图片base64编码加载完成")


    def create_all(self):
        """构造所有类"""
        # 数据库实例化
        self.local_sql_db = AsyncSQLiteDB(str(self.local_data_path))
        self.plugin_sql_db = AsyncSQLiteDB(str(self.plugin_data_path))
        # 剑网三功能实例化
        self.bilei = BiLeidata(self.local_sql_db)
        self.jx3api = JX3APIService(self.conf, self.plugin_sql_db, self.local_sql_db)
        self.jx3box = JX3BOXService(self.conf, self.plugin_sql_db, self.local_sql_db)
        self.event_push = EventPushService(
            cast(Context, self.context),
            self.conf,
            self.local_sql_db,
        )
        self.jx3cmd = MessageBuilder(
            self.server,
            self.jx3api,
            self.jx3box,
            self.bilei,
            self.event_push,
            self.icons,
        )


    async def init_bilei_data(self):
        """初始化避雷数据表"""
        # 连接本地数据
        await self.local_sql_db.connect()
        # 创建bilei表
        await self.local_sql_db.execute("""
        CREATE TABLE IF NOT EXISTS bilei(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            text TEXT,
            time TEXT,
            user TEXT                                           
        )
        """)
    

    async def init_achievement_cache_data(self):
        """初始化资历基础数据缓存表"""
        await self.local_sql_db.execute("""
        CREATE TABLE IF NOT EXISTS achievement_cache(
            key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)


    def ini_command_map(self):
        """初始化指令集"""
        self.command_map = {
            "功能": self. jx3cmd.helps,
            "日常": self. jx3cmd.richang,
            "日常预测": self. jx3cmd.richangyuche,
            "穹野卫": self. jx3cmd.qiongyewei,
            "披风会": self. jx3cmd.pifenghui,
            "云从社": self. jx3cmd.yunchongshe,
            "楚天社": self. jx3cmd.chutianshe,
            "关隘": self. jx3cmd.guanaishouling,
            "赤兔": self. jx3cmd.benrichitu,
            "本周赤兔": self. jx3cmd.benzhouchitu,
            "阵营奉献": self. jx3cmd.zhenyingevent,
            "烟花": self. jx3cmd.yanhuachaxun,
            "刷马": self. jx3cmd.shuma,
            "马场": self. jx3cmd.machang,
            "战绩": self. jx3cmd.zhanji,
            "名剑排行": self. jx3cmd.mingjianpaihang,
            "名剑统计": self. jx3cmd.mingjiantongji,
            "名士五十强": self. jx3cmd.mingshiwushiqiang,
            "老江湖五十强": self. jx3cmd.laojianghuwushiqiang,
            "兵甲藏家五十强": self. jx3cmd.bingjiacangjiawushiqiang,
            "名师五十强": self. jx3cmd.mingshiwushiqiang_mentor,
            "阵营英雄五十强": self. jx3cmd.zhengyingyingxiongwushiqiang,
            "薪火相传五十强": self. jx3cmd.xinhuoxiangchuanwushiqiang,
            "庐园广记一百强": self. jx3cmd.luyuanguangjiyibaiqiang,
            "浩气神兵宝甲五十强": self. jx3cmd.haoqishenbingbaojiawushiqiang,
            "恶人神兵宝甲五十强": self. jx3cmd.erenshenbingbaojiawushiqiang,
            "浩气爱心帮会五十强": self. jx3cmd.haoqiaixinbanghuiwushiqiang,
            "恶人爱心帮会五十强": self. jx3cmd.erenaixinbanghuiwushiqiang,
            "赛季恶人五十强": self. jx3cmd.saijierenwushiqiang,
            "赛季浩气五十强": self. jx3cmd.saijihaoqiwushiqiang,
            "上周恶人五十强": self. jx3cmd.shangzhouerenwushiqiang,
            "上周浩气五十强": self. jx3cmd.shangzhouhaoqiwushiqiang,
            "本周恶人五十强": self. jx3cmd.benzhouerenwushiqiang,
            "本周浩气五十强": self. jx3cmd.benzhouhaoqiwushiqiang,
            "试炼排行": self. jx3cmd.shilianpaixing,
            "阵营拍卖": self. jx3cmd.zhengyingpaimai,
            "的卢": self. jx3cmd.dilujilu,
            "金价": self. jx3cmd.jinjia,
            "物价": self. jx3cmd.wujia,
            "成本": self. jx3cmd.chengbeng,
            "看号": self. jx3cmd.kanhao,
            "帮战": self. jx3cmd.bangzhanjilu,
            "沙盘": self. jx3cmd.shapan,
            "诛恶": self. jx3cmd.zhueevent,
            "名片": self. jx3cmd.jueshemingpian,
            "全名片": self. jx3cmd.shuoyoumingpian,
            "随机秀": self. jx3cmd.shuijimingpian,
            "奇遇": self. jx3cmd.juesheqiyu,
            "查询": self. jx3cmd.juesheqiyu,
            "未出": self. jx3cmd.weizuoqiyu,
            "汇总": self. jx3cmd.qiyuhuizong,
            "近期": self. jx3cmd.jinqiqiyu,
            "统计": self. jx3cmd.qiyutongji,
            "攻略": self. jx3cmd.qiyugonglue,
            "精耐": self. jx3cmd.jingnai,
            "百战": self. jx3cmd.baizhan,
            "成就": self. jx3cmd.chengjiu,
            "角色": self. jx3cmd.jueshe,
            "阵眼": self. jx3cmd.zhenyan,
            "配装": self. jx3cmd.peizhuang,
            "资历排行": self. jx3cmd.zilipaixing,
            "技能": self. jx3cmd.jineng,
            "奇穴": self. jx3cmd.qixue,
            "聊天": self. jx3cmd.liaotian,
            "统战": self. jx3cmd.tongzhanyy,
            "小药": self. jx3cmd.xiaoyao,
            "骗子": self. jx3cmd.pianzhi,
            "花价": self. jx3cmd.huajia,
            "装饰": self. jx3cmd.zhuangshi,
            "器物": self. jx3cmd.qiwu,
            "拜师": self. jx3cmd.baishi,
            "收徒": self. jx3cmd.shoutu,
            "维护": self. jx3cmd.weihu,
            "新闻": self. jx3cmd.xinwen,
            "招募": self. jx3cmd.tuanduizhaomu,
            "团长": self. jx3cmd.tuanzhang,
            "团牌": self. jx3cmd.tuanpai,
            "答案之书": self. jx3cmd.daanzhishu,
            "舔狗语录": self. jx3cmd.tiangou,
            "疯狂星期四": self. jx3cmd.fkxq4,
            "彩虹屁": self. jx3cmd.caihongpi,
            "毒鸡汤": self. jx3cmd.dujitang,
            "朋友圈": self. jx3cmd.pengyouquan,
            "喝什么": self. jx3cmd.heshengme,
            "吃什么": self. jx3cmd.chishengme,
            "骚话": self. jx3cmd.shaohua,
            "渣男语录": self. jx3cmd.zhananyulu,
            "贴吧物价": self. jx3cmd.tiebawujia,
            "818": self. jx3cmd.bagua,
            "科举": self. jx3cmd.keju,
            "区服": self. jx3cmd.zhuangtai,
            "开服": self. jx3cmd.kaifu,
            "技改": self. jx3cmd.jigai,
            "解密": self. jx3cmd.jiemi,
            "副本": self. jx3cmd.fubeng,
            "掉落": self. jx3cmd.diaoluo,

            "宏": self. jx3cmd.hong,
            "资历": self. jx3cmd.zili,
            "交易行": self. jx3cmd.jiaoyihang,

            "事件推送": self.jx3cmd.shijian_tuisong,
            "避雷添加": self.jx3cmd.bilei_add,
            "避雷查看": self.jx3cmd.bilei_all,
            "避雷查询": self.jx3cmd.bilei_select,
            "避雷修改": self.jx3cmd.bilei_update,
            "避雷删除": self.jx3cmd.bilei_delete,
        }


    def parse_message(self, text: str) -> list[str] | None:
        """消息解析"""
        text = text.strip()
        if not text:
            return None

        # 前缀模式
        if self.prefix.get("enable"):
            prefix = self.prefix.get("text")
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
            else:
                # 非前缀消息，直接忽略
                return None

        return text.split()


    async def _call_with_auto_args(self, handler, event: AstrMessageEvent, args: list[str]):
        """指令执行函数"""
        sig = inspect.signature(handler)
        params = list(sig.parameters.values())

        call_args = []
        arg_index = 0

        for p in params:
            if p.name == "self":
                continue

            if p.name == "event":
                call_args.append(event)
                continue

            if arg_index < len(args):
                raw = args[arg_index]
                arg_index += 1
                try:
                    if p.annotation is int:
                        call_args.append(int(raw))
                    elif p.annotation is float:
                        call_args.append(float(raw))
                    else:
                        call_args.append(raw)
                except Exception:
                    call_args.append(p.default)
            else:
                if p.default is not inspect._empty:
                    call_args.append(p.default)
                else:
                    raise ValueError(f"缺少参数: {p.name}")

        # 只允许 coroutine
        return await handler(*call_args)


    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """解析所有消息"""
        if not self.command_map:
            logger.debug("插件尚未初始化完成，忽略消息")
            return
        
        # 获取消息
        parts = self.parse_message(event.message_str)
        if not parts:
            logger.debug("未触发指令，忽略消息")
            return

        cmd, *args = parts
        handler = self.command_map.get(cmd)
        if not handler:
            logger.debug("指令函数为空，忽略消息")
            return

        try:
            event.stop_event()
            ret = await self._call_with_auto_args(handler, event, args)
            if ret is not None:
                yield ret
        except Exception as e:
            logger.exception(f"指令执行失败: {cmd}, error={e}")
            yield event.plain_result("参数错误或执行失败")







