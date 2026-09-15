"""使用范围控制单测：三种模式 × 名单匹配 × 私聊开关。

使用真实 AsyncSQLiteDB（临时文件），覆盖建表、配置读写、
名单增删与 is_allowed 判定矩阵。
"""

import pytest

from astrbot_plugin_jx3.core.access_control import (
    AccessControlService,
    MODE_ALL,
    MODE_BLACKLIST,
    MODE_WHITELIST,
    REASON_MODE,
    REASON_PRIVATE,
)
from astrbot_plugin_jx3.core.sqlite import AsyncSQLiteDB

pytestmark = pytest.mark.asyncio

SESSION = "default:GroupMessage:10001"
GROUP = "10001"


@pytest.fixture()
async def service(tmp_path):
    db = AsyncSQLiteDB(str(tmp_path / "test.db"))
    await db.connect()
    svc = AccessControlService(db)
    await svc.initialize()
    yield svc
    await db.close()


class TestDefaults:
    async def test_default_mode_all_allows_everything(self, service):
        assert service.mode == MODE_ALL
        assert service.is_allowed(SESSION, GROUP) == (True, "")
        assert service.is_allowed("default:FriendMessage:1", "") == (True, "")


class TestPrivateSwitch:
    async def test_private_disabled(self, service):
        await service.set_config(private_allowed=False)
        allowed, reason = service.is_allowed("default:FriendMessage:1", "")
        assert allowed is False
        assert reason == REASON_PRIVATE

    async def test_private_switch_does_not_affect_groups(self, service):
        await service.set_config(private_allowed=False)
        assert service.is_allowed(SESSION, GROUP) == (True, "")


class TestWhitelist:
    async def test_empty_whitelist_denies_all_groups(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        allowed, reason = service.is_allowed(SESSION, GROUP)
        assert (allowed, reason) == (False, REASON_MODE)

    async def test_group_id_entry_allows(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        await service.add_entry(GROUP, "主群")
        assert service.is_allowed(SESSION, GROUP) == (True, "")

    async def test_full_session_entry_allows(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        await service.add_entry(SESSION)
        assert service.is_allowed(SESSION, GROUP) == (True, "")

    async def test_other_group_still_denied(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        await service.add_entry(GROUP)
        assert service.is_allowed("default:GroupMessage:20002", "20002") == (
            False,
            REASON_MODE,
        )


class TestBlacklist:
    async def test_empty_blacklist_allows_all(self, service):
        await service.set_config(mode=MODE_BLACKLIST)
        assert service.is_allowed(SESSION, GROUP) == (True, "")

    async def test_listed_group_denied(self, service):
        await service.set_config(mode=MODE_BLACKLIST)
        await service.add_entry(GROUP)
        assert service.is_allowed(SESSION, GROUP) == (False, REASON_MODE)

    async def test_unlisted_group_allowed(self, service):
        await service.set_config(mode=MODE_BLACKLIST)
        await service.add_entry("99999")
        assert service.is_allowed(SESSION, GROUP) == (True, "")


class TestEntries:
    async def test_add_delete_roundtrip(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        await service.add_entry(GROUP, "备注")
        assert service.is_allowed(SESSION, GROUP) == (True, "")
        await service.delete_entry(GROUP)
        assert service.is_allowed(SESSION, GROUP) == (False, REASON_MODE)

    async def test_add_entry_rejects_blank(self, service):
        with pytest.raises(ValueError):
            await service.add_entry("   ")

    async def test_invalid_mode_rejected(self, service):
        with pytest.raises(ValueError):
            await service.set_config(mode="grey")

    async def test_config_persisted_across_reload(self, service, tmp_path):
        await service.set_config(mode=MODE_BLACKLIST, reply_on_deny=True)
        await service.add_entry(GROUP)
        await service._load()
        assert service.mode == MODE_BLACKLIST
        assert service.reply_on_deny is True
        assert service.is_allowed(SESSION, GROUP) == (False, REASON_MODE)


class TestRecordUsage:
    async def test_group_usage_recorded_with_name(self, service):
        await service.record_usage(SESSION, GROUP, "测试群")
        groups = await service.list_recent_groups()
        assert len(groups) == 1
        assert groups[0]["group_id"] == GROUP
        assert groups[0]["group_name"] == "测试群"

    async def test_empty_name_does_not_overwrite(self, service):
        """抓取失败（空名）不能抹掉已有群名。"""
        await service.record_usage(SESSION, GROUP, "测试群")
        await service.record_usage(SESSION, GROUP, "")
        groups = await service.list_recent_groups()
        assert groups[0]["group_name"] == "测试群"

    async def test_missing_names_candidates(self, service):
        await service.record_usage(SESSION, GROUP, "")
        missing = await service.list_groups_missing_names()
        assert GROUP in missing
        await service.update_group_name(GROUP, "补抓成功")
        assert GROUP not in await service.list_groups_missing_names()

    async def test_session_allowed_unknown_session_defaults_true(self, service):
        """升级前的存量订阅没有类型记录，默认放行避免推送消失。"""
        assert await service.session_allowed("default:GroupMessage:0") is True


class TestDenyText:
    async def test_private_reason_text(self, service):
        assert "私聊" in service.deny_text(REASON_PRIVATE)

    async def test_mode_reason_texts(self, service):
        await service.set_config(mode=MODE_WHITELIST)
        assert "未授权" in service.deny_text(REASON_MODE)
        await service.set_config(mode=MODE_BLACKLIST)
        assert "停用" in service.deny_text(REASON_MODE)
