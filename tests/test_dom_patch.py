"""DOM 视口裁剪 patch 单元测试。"""

import logging

from browser_use.dom.service import DomService
from browser_use_ext.dom_patch import patch_viewport_threshold


class _FakeBrowserSession:
    logger = logging.getLogger("test_dom_patch")


def test_patch_overrides_viewport_threshold():
    patch_viewport_threshold(200)
    ds = DomService(browser_session=_FakeBrowserSession())
    assert ds.viewport_threshold == 200


def test_patch_respects_explicit_value():
    patch_viewport_threshold(200)
    ds = DomService(browser_session=_FakeBrowserSession(), viewport_threshold=500)
    assert ds.viewport_threshold == 500


def test_patch_idempotent_update():
    patch_viewport_threshold(200)
    patch_viewport_threshold(0)
    ds = DomService(browser_session=_FakeBrowserSession())
    assert ds.viewport_threshold == 0
