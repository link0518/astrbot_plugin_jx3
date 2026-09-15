"""管理页静态完整性守卫。

把两类已在生产上踩过的前端 bug 固化为 CI 拦截：
1. app.js 通过 byId() 引用的元素 id 必须存在于 index.html
   （3.7.0/3.7.1 曾因 errors-panel 未落盘导致模块加载中断）；
2. bridge.apiGet/apiPost 的端点不允许内联查询串——AstrBot 桥接会把
   端点按 "/" 分段后 encodeURIComponent，"?days=7" 会被编码进路径导致 404
   （3.7.2 指令统计页签因此无法加载）。
"""

import re
from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parent.parent / "pages" / "server-management"


def _load_sources():
    js = (PAGES_DIR / "app.js").read_text(encoding="utf-8")
    html = (PAGES_DIR / "index.html").read_text(encoding="utf-8")
    return js, html


def test_byid_targets_exist_in_html():
    js, html = _load_sources()
    js_ids = set(re.findall(r'byId\("([^"]+)"\)', js))
    html_ids = set(re.findall(r'id="([^"]+)"', html))
    # JS 动态创建并赋 id 的元素不要求出现在 HTML 里。
    dynamic_ids = set(re.findall(r"""\.id\s*=\s*["']([^"']+)["']""", js))
    missing = js_ids - html_ids - dynamic_ids
    assert not missing, f"app.js 引用了 index.html 中不存在的元素 id: {sorted(missing)}"


def test_no_inline_query_string_in_bridge_endpoint():
    js, _ = _load_sources()
    bad = re.findall(
        r"""bridge\.api(?:Get|Post)\(\s*[`"']/?([^`"']*\?[^`"']*)[`"']""",
        js,
    )
    assert not bad, (
        "桥接端点不允许内联查询串（会被 encodeURIComponent 编码进路径导致 404），"
        f"请改用第二参数传 params: {bad}"
    )


def test_tab_buttons_have_matching_panels():
    """每个 data-tab 页签按钮都要有对应的 <section id="{tab}-panel">。"""
    _, html = _load_sources()
    tabs = set(re.findall(r'data-tab="([^"]+)"', html))
    panels = set(re.findall(r'id="([^"]+)-panel"', html))
    orphan_tabs = tabs - panels
    orphan_panels = panels - tabs
    assert not orphan_tabs, f"页签按钮缺少对应面板: {sorted(orphan_tabs)}"
    assert not orphan_panels, f"面板缺少对应页签按钮: {sorted(orphan_panels)}"
