import asyncio
import re
import unittest
from pathlib import Path

from jinja2 import ChainableUndefined, Environment

from core.template import TemplateRepository


ROOT = Path(__file__).parent.parent
TEMPLATE_ROOT = ROOT / "templates"
SPECIAL_PAGE_STYLES = {
    "baizhan",
    "chengbeng",
    "chengjiu",
    "fubenjilu",
    "helps",
    "jiaoyihang",
    "juesheliaotian",
    "richangyuche",
    "wujia",
    "xingxiashijian",
    "zhanji",
    "zili",
    "zilipaixing",
}


class TemplateRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = TemplateRepository(TEMPLATE_ROOT)

    def test_all_pages_compose_to_valid_jinja_documents(self):
        pages = sorted((TEMPLATE_ROOT / "pages").glob("*.html"))
        page_styles = sorted((TEMPLATE_ROOT / "styles" / "pages").glob("*.css"))
        self.assertEqual(46, len(pages))
        self.assertEqual(
            SPECIAL_PAGE_STYLES,
            {style.stem for style in page_styles},
        )

        environment = Environment(undefined=ChainableUndefined)
        empty_context = {
            "data": {},
            "icons": {"img": {}, "sect": {}, "serendipity": {}},
            "items": [],
            "summary": {},
        }
        for page in pages:
            with self.subTest(page=page.name):
                fragment = page.read_text(encoding="utf-8")
                for document_tag in ("!DOCTYPE", "html", "head", "style", "body"):
                    self.assertIsNone(
                        re.search(rf"<{document_tag}(?:\s|>)", fragment, re.IGNORECASE)
                    )

                template = asyncio.run(self.repository.get(page.name))
                self.assertIn("<!DOCTYPE html>", template)
                self.assertIn("<body", template)
                self.assertIn("</body>", template)
                self.assertNotIn("<!--__PAGE_CONTENT__-->", template)
                self.assertNotIn("/*__PAGE_CSS__*/", template)
                self.assertNotIn("/* @component", template)
                self.assertNotIn("/* @endcomponent */", template)
                rendered = environment.from_string(template).render(empty_context)
                self.assertIn("</html>", rendered)

    def test_repeated_page_patterns_use_shared_components(self):
        components = (TEMPLATE_ROOT / "styles" / "components.css").read_text(
            encoding="utf-8"
        )
        for selector in (
            ".data-table",
            ".data-cell--rank",
            ".card-grid",
            ".ability-card",
            ".collection-card",
            ".object-card",
        ):
            self.assertIn(selector, components)

        expected_components = {
            "bilei.html": "data-table",
            "rank_role.html": "data-cell--rank",
            "jineng.html": "ability-card",
            "juesheqiyu.html": "collection-card",
            "qiwu.html": "object-card",
        }
        for name, component in expected_components.items():
            with self.subTest(page=name):
                fragment = (TEMPLATE_ROOT / "pages" / name).read_text(
                    encoding="utf-8"
                )
                self.assertIn(component, fragment)
                page_style = TEMPLATE_ROOT / "styles" / "pages" / (
                    f"{Path(name).stem}.css"
                )
                self.assertFalse(page_style.exists())

    def test_image_templates_do_not_define_responsive_breakpoints(self):
        for style in sorted((TEMPLATE_ROOT / "styles").rglob("*.css")):
            with self.subTest(style=style.relative_to(TEMPLATE_ROOT)):
                content = style.read_text(encoding="utf-8")
                self.assertIsNone(
                    re.search(r"@media\s*(?:screen\s+and\s+)?\([^)]*width", content)
                )

        base = (TEMPLATE_ROOT / "styles" / "base.css").read_text(encoding="utf-8")
        self.assertIn("min-width: calc(var(--jx3-page-width) + 94px)", base)
        self.assertIn("width: var(--jx3-page-width)", base)
        self.assertNotIn("100vw", base)

    def test_only_declared_component_blocks_are_injected(self):
        table_page = asyncio.run(self.repository.get("bilei.html"))
        self.assertIn(".data-table--spaced", table_page)
        self.assertNotIn(".ability-card__head", table_page)
        self.assertNotIn(".object-card__footer", table_page)

        ability_page = asyncio.run(self.repository.get("jineng.html"))
        self.assertIn(".card-grid", ability_page)
        self.assertIn(".ability-card__head", ability_page)
        self.assertNotIn(".data-table--spaced", ability_page)
        self.assertNotIn(".object-card__footer", ability_page)

        object_page = asyncio.run(self.repository.get("qiwu.html"))
        self.assertIn(".object-card__footer", object_page)
        self.assertNotIn(".ability-card__head", object_page)

    def test_wujia_groups_follow_the_api_names_instead_of_list_positions(self):
        """万宝楼分组在真实返回中位于列表末尾，且在售组名为“在售期”。"""
        template = asyncio.run(self.repository.get("wujia.html"))
        rendered = Environment(undefined=ChainableUndefined).from_string(template).render(
            {
                "icons": {"img": {}, "sect": {}, "serendipity": {}},
                "name": "浮屠明音礼盒",
                "alias": "",
                "view": "",
                "desc": "",
                "category": "外观礼盒",
                "date": "2018-08-24",
                "retail": 888,
                "list": [
                    {"name": "电信区", "list": []},
                    {"name": "双线区", "list": []},
                    {"name": "无界区", "list": []},
                    {
                        "name": "梦江南",
                        "list": [
                            {
                                "date": "QUERY-MARKER",
                                "server": "梦江南",
                                "value": 4700,
                                "sale": 4,
                            }
                        ],
                    },
                    {"name": "公示期", "list": []},
                    {
                        "name": "在售期",
                        "list": [
                            {
                                "date": "SALE-MARKER",
                                "zone": "电信区",
                                "server": "梦江南",
                                "value": 5188,
                            }
                        ],
                    },
                ],
            }
        )

        sale_start = rendered.index('<div class="table-card sale">')
        query_start = rendered.index('<div class="table-card query">')
        next_card = rendered.index('<div class="table-card">', query_start)
        sale_section = rendered[sale_start:query_start]
        query_section = rendered[query_start:next_card]

        self.assertIn("SALE-MARKER", sale_section)
        self.assertNotIn("QUERY-MARKER", sale_section)
        self.assertIn("查询区服：梦江南", re.sub(r"\s+", "", query_section))
        self.assertIn("QUERY-MARKER", query_section)
        self.assertNotIn("SALE-MARKER", query_section)

    def test_known_dark_theme_text_uses_shared_color_tokens(self):
        expected = {
            "jiaoyihang.css": (".item-name", ".price", ".sample"),
            "juesheliaotian.css": (".role-col", ".message-col"),
            "zilipaixing.css": (".force", ".role-name-col", ".server-col"),
        }
        for name, selectors in expected.items():
            with self.subTest(style=name):
                content = (TEMPLATE_ROOT / "styles" / "pages" / name).read_text(
                    encoding="utf-8"
                )
                for selector in selectors:
                    block = re.search(
                        rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}",
                        content,
                        re.DOTALL,
                    )
                    self.assertIsNotNone(block)
                    self.assertIn("var(--jx3-", block.group("body"))

    def test_rejects_unknown_component_declaration(self):
        components = (TEMPLATE_ROOT / "styles" / "components.css").read_text(
            encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            self.repository._select_component_styles(components, {"missing"})

    def test_cache_returns_same_template_instance(self):
        first = asyncio.run(self.repository.get("helps.html"))
        shared_assets = self.repository._shared_assets
        second = asyncio.run(self.repository.get("helps.html"))
        self.assertIs(first, second)
        asyncio.run(self.repository.get("bilei.html"))
        self.assertIs(shared_assets, self.repository._shared_assets)

        self.repository.clear()
        self.assertIsNone(self.repository._shared_assets)

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.get("../helps.html"))

    def test_help_page_catalogue_structure(self):
        fragment = (TEMPLATE_ROOT / "pages" / "helps.html").read_text(
            encoding="utf-8"
        )
        categories = re.findall(
            r'<div class="section-title">([^<]+)</div>', fragment
        )
        features = re.findall(r'<div class="feature(?:\s|\")', fragment)
        commands = re.findall(r'<span class="command">(.*?)</span>', fragment)

        self.assertEqual(
            [
                "活动情报",
                "名剑相关",
                "排行榜单",
                "物价交易",
                "阵营战场",
                "角色名片",
                "奇遇相关",
                "百战记录",
                "角色信息",
                "资历相关",
                "心法配装",
                "游戏社区",
                "百度贴吧",
                "系统工具",
                "杂项功能",
                "避雷功能",
                "推送功能",
            ],
            categories,
        )
        self.assertEqual(69, len(features))
        self.assertEqual(105, len(commands))
        self.assertEqual(105, len(set(commands)))
        self.assertIn("共 17 个功能分类 · 69 项功能 · 105 条指令", fragment)


if __name__ == "__main__":
    unittest.main()
