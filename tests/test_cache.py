"""缓存层纯逻辑单测：键构造、敏感参数剔除、TTL 与容量校验、默认策略。

只用 CacheService 的类方法 / 轻量实例属性，不连接数据库、不触发网络。
"""

import pytest

from astrbot_plugin_jx3.core.cache import CacheService


def _bare_service(settings=None):
    """绕过 __init__ 构造只含 _settings 的裸实例，用于 get_ttl 测试。"""
    svc = object.__new__(CacheService)
    svc._settings = dict(settings or {})
    return svc


class TestBuildApiKey:
    def test_sensitive_params_excluded(self):
        """token/ticket 等敏感值不参与缓存键，避免凭据轮换导致缓存全失效。"""
        params_clean = {"server": "梦江南", "name": "晏卿卿"}
        params_dirty = {
            "server": "梦江南",
            "name": "晏卿卿",
            "token": "SECRET-A",
            "ticket": "T-1",
        }
        params_other_secret = {
            "server": "梦江南",
            "name": "晏卿卿",
            "token": "SECRET-B",
        }
        key_clean = CacheService.build_api_key("/role/detail", params_clean)
        assert CacheService.build_api_key("/role/detail", params_dirty) == key_clean
        assert (
            CacheService.build_api_key("/role/detail", params_other_secret)
            == key_clean
        )

    def test_param_order_irrelevant(self):
        key_a = CacheService.build_api_key("/x", {"a": 1, "b": 2})
        key_b = CacheService.build_api_key("/x", {"b": 2, "a": 1})
        assert key_a == key_b

    def test_different_business_params_differ(self):
        key_a = CacheService.build_api_key("/x", {"name": "甲"})
        key_b = CacheService.build_api_key("/x", {"name": "乙"})
        assert key_a != key_b

    def test_endpoint_participates(self):
        key_a = CacheService.build_api_key("/a", {"name": "甲"})
        key_b = CacheService.build_api_key("/b", {"name": "甲"})
        assert key_a != key_b


class TestValidateTtl:
    def test_valid_range(self):
        assert CacheService._validate_ttl(0) == 0
        assert CacheService._validate_ttl("300") == 300
        assert (
            CacheService._validate_ttl(CacheService.MAX_TTL_SECONDS)
            == CacheService.MAX_TTL_SECONDS
        )

    @pytest.mark.parametrize("bad", [-1, CacheService.MAX_TTL_SECONDS + 1])
    def test_out_of_range(self, bad):
        with pytest.raises(ValueError):
            CacheService._validate_ttl(bad)

    @pytest.mark.parametrize("bad", [True, False, "abc", None])
    def test_non_integer_types(self, bad):
        with pytest.raises(ValueError):
            CacheService._validate_ttl(bad)

    def test_float_truncated_to_int(self):
        """实现现状：float 经 int() 截断接受（1.5 -> 1），不抛错。"""
        assert CacheService._validate_ttl(1.5) == 1


class TestValidateLimits:
    def test_memory_limit_bounds(self):
        assert CacheService._validated_memory_limit_mb(16) == 16
        with pytest.raises(ValueError):
            CacheService._validated_memory_limit_mb(0)
        with pytest.raises(ValueError):
            CacheService._validated_memory_limit_mb(1025)
        with pytest.raises(ValueError):
            CacheService._validated_memory_limit_mb(True)

    def test_api_entry_limit_bounds(self):
        assert CacheService._validated_api_entry_limit(256) == 256
        with pytest.raises(ValueError):
            CacheService._validated_api_entry_limit(0)
        with pytest.raises(ValueError):
            CacheService._validated_api_entry_limit(100001)

    def test_image_limit_bounds(self):
        assert CacheService._validated_image_limit_mb(512) == 512
        with pytest.raises(ValueError):
            CacheService._validated_image_limit_mb(0)
        with pytest.raises(ValueError):
            CacheService._validated_image_limit_mb(10241)


class TestGetTtl:
    def test_defaults(self):
        svc = _bare_service()
        assert svc.get_ttl("api", "/role/detail") == CacheService.DEFAULT_API_TTL
        assert svc.get_ttl("image", "战绩") == CacheService.DEFAULT_IMAGE_TTL

    def test_no_cache_api_defaults(self):
        """随机内容接口安全默认 0 秒。"""
        svc = _bare_service()
        assert svc.get_ttl("api", "/card/random") == 0
        assert svc.get_ttl("api", "/saohua/random") == 0

    def test_bilei_images_default_zero(self):
        """会话避雷图片默认不缓存，避免修改记录后展示旧图。"""
        svc = _bare_service()
        assert svc.get_ttl("image", "避雷查看") == 0
        assert svc.get_ttl("image", "避雷查询") == 0

    def test_specific_override_wins(self):
        svc = _bare_service({("api", "/role/detail"): 60})
        assert svc.get_ttl("api", "/role/detail") == 60

    def test_wildcard_default_override(self):
        svc = _bare_service({("api", "*"): 120})
        assert svc.get_ttl("api", "/role/detail") == 120
        # 具体项仍优先于通配
        svc = _bare_service({("api", "*"): 120, ("api", "/role/detail"): 30})
        assert svc.get_ttl("api", "/role/detail") == 30


class TestNormalized:
    def test_dict_sorted_and_nested(self):
        value = {"b": {"y": 2, "x": 1}, "a": [3, {"k": "v"}]}
        json_text = CacheService._json(value)
        assert json_text.index('"a"') < json_text.index('"b"')
        assert json_text.index('"x"') < json_text.index('"y"')

    def test_strip_sensitive_nested(self):
        value = {"outer": {"token": "S", "keep": 1}, "ticket": "T"}
        normalized = CacheService._normalized(value, strip_sensitive=True)
        assert normalized == {"outer": {"keep": 1}}

    def test_unknown_types_stringified(self):
        class Thing:
            def __str__(self):
                return "thing!"

        assert CacheService._normalized({"obj": Thing()}) == {"obj": "thing!"}
