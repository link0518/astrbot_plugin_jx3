"""JX3API 数据服务（自 core/jx3api_data.py 拆分）。

按业务域分为 base / ranks / qiyu / role / trade / misc 六个 mixin，
对外仍暴露同一个 ``JX3APIService``，方法签名与行为不变。
"""

from .base import BaseService
from .misc import MiscMixin
from .qiyu import QiyuMixin
from .ranks import RanksMixin
from .role import RoleMixin
from .trade import TradeMixin


class JX3APIService(
    BaseService, RanksMixin, QiyuMixin, RoleMixin, TradeMixin, MiscMixin
):
    """聚合各业务域 mixin 的 JX3API 数据服务。"""


__all__ = ["JX3APIService"]
