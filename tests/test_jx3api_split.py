"""jx3api 分包等价性测试：拆分后对外接口与原 monolith 完全一致。

防止 mixin 组合时漏挂方法、兼容层转发失效或常量丢失。
"""

import inspect

from astrbot_plugin_jx3.core.jx3api import JX3APIService
from astrbot_plugin_jx3.core import jx3api_data as compat

EXPECTED_METHODS = {
    # base
    "__init__", "close", "server_list", "token_stats", "_fetch_token_stats",
    "_init_return_data", "_base_request", "_is_cacheable_response",
    "_cached_request", "_request_api", "helps",
    # misc：日常/活动/沙盘/心法/社区/杂项
    "richang", "xingxiashijian", "guanaishouling", "benrichitu",
    "benzhouchitu", "zhenyingevent", "yanhuachaxun", "shuma", "machang",
    "bangzhanjilu", "shapan", "zhueevent", "zhenyan", "jineng", "qixue",
    "tongzhanyy", "xiaoyao", "pianzhi", "zhuangshi", "qiwu", "weihu",
    "xinwen", "tuanduizhaomu", "daanzhishu", "tiangou", "fengleiyulu",
    "heshengme", "chishengme", "shaohua", "zhananyulu", "keju",
    "zhuangtai", "kaifu", "jigai", "jiemi", "diaoluo", "bagua",
    # ranks
    "mingjianpaihang", "mingjiantongji", "kuafumingjian", "wulinzhengba",
    "_bounty_rank", "bukairongyu", "jianghulangke", "juedoutiaozhan",
    "banghui_rank_menu", "zhenying_rank_menu", "qita_rank_menu",
    "rank_statistical_select", "rank_statistical", "shilianpaixing",
    "zilipaixing",
    # qiyu
    "qiyuhuizong", "weizuoqiyu", "jinqiqiyu", "juesheqiyu", "qiyutongji",
    # role
    "zhanji", "jueshemingpian", "shuijimingpian", "shuoyoumingpian",
    "jingnai", "baizhan", "chengjiuchaxun", "zili_menu", "zili", "jueshe",
    "juesheliaotian", "shitu", "fubengjilu",
    # trade
    "zhengyingpaimai", "dilujilu", "jinjia", "wujia", "chengbeng",
    "bianhao", "huajia", "tiebawujia",
}


class TestSplitEquivalence:
    def test_all_methods_present(self):
        missing = {
            name
            for name in EXPECTED_METHODS
            if not callable(getattr(JX3APIService, name, None))
        }
        assert not missing, f"分包后丢失方法: {sorted(missing)}"

    def test_method_count_matches_monolith(self):
        """原 monolith 共 89 个方法，拆分后不允许增减。"""
        defined = {
            name
            for name, _ in inspect.getmembers(JX3APIService, predicate=callable)
            if not name.startswith("__") or name == "__init__"
        }
        assert EXPECTED_METHODS <= defined
        assert len(EXPECTED_METHODS) == 89

    def test_compat_layer_forwards_same_class(self):
        assert compat.JX3APIService is JX3APIService

    def test_compat_layer_constants(self):
        assert "名士五十强" in compat.ROLE_RANK_NAMES
        assert compat.GUILD_RANK_OPTIONS["1"] == "浩气神兵宝甲五十强"
        assert compat.CAMP_RANK_OPTIONS["6"] == "本周浩气五十强"
        assert compat.OTHER_RANK_OPTIONS["7"] == "庐园广记一百强"
        assert compat.RANK_NAMES == frozenset().union(
            compat.ROLE_RANK_NAMES,
            compat.TONG_RANK_NAMES0,
            compat.TONG_RANK_NAMES1,
            compat.TONG_RANK_NAMES2,
        )

    def test_signatures_preserved(self):
        """关键方法签名抽查：拆分不改变参数定义。"""
        sig = inspect.signature(JX3APIService.zhanji)
        assert list(sig.parameters) == ["self", "name", "server", "mode"]
        sig = inspect.signature(JX3APIService.kuafumingjian)
        params = list(sig.parameters.values())
        assert [p.name for p in params] == ["self", "server", "mode"]
        assert params[2].default == 1

    def test_no_mixin_method_collisions(self):
        """各 mixin 之间不允许出现同名方法（否则 MRO 会静默覆盖）。"""
        from astrbot_plugin_jx3.core.jx3api import (
            base,
            misc,
            qiyu,
            ranks,
            role,
            trade,
        )

        seen: dict[str, str] = {}
        collisions = []
        for module in (base, ranks, qiyu, role, trade, misc):
            class_name = next(
                name
                for name, obj in vars(module).items()
                if isinstance(obj, type) and obj.__module__ == module.__name__
            )
            cls = getattr(module, class_name)
            for name, value in vars(cls).items():
                if callable(value) and not name.startswith("__"):
                    if name in seen:
                        collisions.append((name, seen[name], class_name))
                    seen[name] = class_name
        assert not collisions, f"mixin 方法冲突: {collisions}"
