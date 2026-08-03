import asyncio
import re
import unittest
from pathlib import Path

from jinja2 import ChainableUndefined, Environment

from core.template import TemplateRepository


ROOT = Path(__file__).parent.parent
TEMPLATE_ROOT = ROOT / "templates"


class TemplateRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = TemplateRepository(TEMPLATE_ROOT)

    def test_all_pages_compose_to_valid_jinja_documents(self):
        pages = sorted((TEMPLATE_ROOT / "pages").glob("*.html"))
        page_styles = sorted((TEMPLATE_ROOT / "styles" / "pages").glob("*.css"))
        self.assertEqual(46, len(pages))
        self.assertEqual(
            {page.stem for page in pages},
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
                rendered = environment.from_string(template).render(empty_context)
                self.assertIn("</html>", rendered)

    def test_cache_returns_same_template_instance(self):
        first = asyncio.run(self.repository.get("helps.html"))
        second = asyncio.run(self.repository.get("helps.html"))
        self.assertIs(first, second)

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
