"""模板组装快照测试：全部页面模板必须能组装为完整 HTML。

不做像素级渲染（依赖浏览器环境），只做结构断言：
组装成功、无未替换标记、标题正确提取、声明的公共组件都存在。
模板元数据写法或组件名拼错时本测试会直接失败。
"""

import re
from pathlib import Path

import pytest

from astrbot_plugin_jx3.core.template import (
    TemplateRepository,
    _PAGE_COMPONENTS_PATTERN,
    _TITLE_PATTERN,
)

# asyncio_mode=auto 自动处理 async 测试，无需显式标记。

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"
PAGE_NAMES = sorted(path.name for path in TEMPLATE_ROOT.glob("pages/*.html"))

assert PAGE_NAMES, "未找到任何页面模板，测试失去意义"


@pytest.fixture()
def repo():
    return TemplateRepository(TEMPLATE_ROOT)


@pytest.mark.parametrize("page_name", PAGE_NAMES)
async def test_page_assembles(repo, page_name):
    template = await repo.get(page_name)
    # 组装器内部已校验标记全部替换，这里再兜底关键结构。
    assert "<html" in template
    assert "</html>" in template
    assert "__PAGE_ID__" not in template
    assert "<!--__PAGE_CONTENT__-->" not in template


@pytest.mark.parametrize("page_name", PAGE_NAMES)
async def test_page_title_extracted(repo, page_name):
    raw = (TEMPLATE_ROOT / "pages" / page_name).read_text(encoding="utf-8")
    match = _TITLE_PATTERN.match(raw)
    template = await repo.get(page_name)
    if match:
        expected = match.group(1).strip()
        assert f"<title>{expected}</title>" in template
    else:
        # 未声明标题时使用默认标题
        assert "<title>剑网三数据查询</title>" in template


def test_declared_components_exist():
    """页面 template-components 元数据里声明的组件必须在 components.css 有定义。"""
    component_source = (TEMPLATE_ROOT / "styles" / "components.css").read_text(
        encoding="utf-8"
    )
    defined = set(
        re.findall(r"/\* @component ([a-z0-9-]+) \*/", component_source)
    )
    for path in TEMPLATE_ROOT.glob("pages/*.html"):
        raw = path.read_text(encoding="utf-8")
        content = _TITLE_PATTERN.sub("", raw, count=1)
        match = _PAGE_COMPONENTS_PATTERN.match(content)
        if not match:
            continue
        requested = set(match.group(1).split())
        unknown = requested - defined
        assert not unknown, f"{path.name} 声明了不存在的组件: {sorted(unknown)}"


def test_duplicate_component_definitions():
    """components.css 内组件名不允许重复（组装器会抛错）。"""
    component_source = (TEMPLATE_ROOT / "styles" / "components.css").read_text(
        encoding="utf-8"
    )
    names = re.findall(r"/\* @component ([a-z0-9-]+) \*/", component_source)
    assert len(names) == len(set(names)), "components.css 存在重复组件名"


async def test_invalid_template_name_rejected(repo):
    with pytest.raises(ValueError):
        await repo.get("../escape.html")
    with pytest.raises(ValueError):
        await repo.get("not-html.txt")


async def test_missing_template_raises(repo):
    with pytest.raises(FileNotFoundError):
        await repo.get("does-not-exist.html")
