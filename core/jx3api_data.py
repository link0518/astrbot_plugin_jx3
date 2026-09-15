"""兼容层：JX3APIService 已拆分到 ``core/jx3api/`` 分包。

本文件仅做转发，保持既有 ``from .core.jx3api_data import JX3APIService``
导入路径不变；新代码请直接从 ``core.jx3api`` 导入。
"""

from .jx3api import JX3APIService
from .jx3api.ranks import (
    CAMP_RANK_OPTIONS,
    GUILD_RANK_OPTIONS,
    OTHER_RANK_OPTIONS,
    RANK_NAMES,
    ROLE_RANK_NAMES,
    TONG_RANK_NAMES0,
    TONG_RANK_NAMES1,
    TONG_RANK_NAMES2,
)

__all__ = [
    "JX3APIService",
    "ROLE_RANK_NAMES",
    "TONG_RANK_NAMES0",
    "TONG_RANK_NAMES1",
    "TONG_RANK_NAMES2",
    "GUILD_RANK_OPTIONS",
    "CAMP_RANK_OPTIONS",
    "OTHER_RANK_OPTIONS",
    "RANK_NAMES",
]
