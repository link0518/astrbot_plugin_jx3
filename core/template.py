import asyncio
import re
from pathlib import Path

import aiofiles


_TITLE_PATTERN = re.compile(
    r"\A\{# template-title: (.*?) #\}\r?\n",
)


class TemplateRepository:
    """将公共布局、设计系统和页面片段组装为完整 Jinja 模板。"""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _read(self, path: Path) -> str:
        async with aiofiles.open(path, "r", encoding="utf-8") as file:
            return await file.read()

    def _page_path(self, template_name: str) -> Path:
        name = Path(template_name)
        if name.name != template_name or name.suffix.lower() != ".html":
            raise ValueError(f"非法模板名称: {template_name}")
        return self.root / "pages" / name.name

    async def get(self, template_name: str) -> str:
        """读取并缓存组装后的完整模板字符串。"""
        cached = self._cache.get(template_name)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._cache.get(template_name)
            if cached is not None:
                return cached

            page_path = self._page_path(template_name)
            if not page_path.exists():
                # 兼容迁移期间尚未拆分的旧模板。
                legacy_path = self.root / template_name
                if not legacy_path.exists():
                    raise FileNotFoundError(f"模板文件不存在: {page_path}")
                template = await self._read(legacy_path)
                self._cache[template_name] = template
                return template

            page_css_path = self.root / "styles" / "pages" / f"{page_path.stem}.css"
            read_tasks = [
                self._read(self.root / "layouts" / "base.html"),
                self._read(self.root / "styles" / "tokens.css"),
                self._read(self.root / "styles" / "base.css"),
                self._read(page_path),
                self._read(page_css_path),
                self._read(self.root / "styles" / "components.css"),
            ]
            base, tokens, base_css, page, page_css, components = await asyncio.gather(
                *read_tasks
            )

            title_match = _TITLE_PATTERN.match(page)
            title = title_match.group(1).strip() if title_match else "剑网三数据查询"
            content = _TITLE_PATTERN.sub("", page, count=1)

            template = (
                base.replace("__PAGE_ID__", page_path.stem)
                .replace("<!--__PAGE_TITLE__-->", title)
                .replace("/*__TOKENS_CSS__*/", tokens)
                .replace("/*__BASE_CSS__*/", base_css)
                .replace("/*__PAGE_CSS__*/", page_css)
                .replace("/*__COMPONENTS_CSS__*/", components)
                .replace("<!--__PAGE_CONTENT__-->", content)
            )

            unresolved = (
                "__PAGE_ID__",
                "<!--__PAGE_TITLE__-->",
                "/*__TOKENS_CSS__*/",
                "/*__BASE_CSS__*/",
                "/*__PAGE_CSS__*/",
                "/*__COMPONENTS_CSS__*/",
                "<!--__PAGE_CONTENT__-->",
            )
            if any(marker in template for marker in unresolved):
                raise ValueError(f"模板组装失败，存在未替换标记: {template_name}")

            self._cache[template_name] = template
            return template

    def clear(self) -> None:
        """清理内存缓存，主要用于开发和测试。"""
        self._cache.clear()


_TEMPLATE_ROOT = Path(__file__).parent.parent / "templates"
_TEMPLATE_REPOSITORY = TemplateRepository(_TEMPLATE_ROOT)


async def load_template(template_name: str) -> str:
    return await _TEMPLATE_REPOSITORY.get(template_name)
