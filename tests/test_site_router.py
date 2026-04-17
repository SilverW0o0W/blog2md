import unittest
from pathlib import Path
from unittest.mock import patch

from blog2md.site_router import convert_url_to_md, select_site


class SiteRouterTests(unittest.TestCase):
    def test_select_site_by_domain(self) -> None:
        self.assertEqual(select_site("https://www.cnblogs.com/a/p/1.html"), "cnblogs")
        self.assertEqual(select_site("https://mp.weixin.qq.com/s/abc"), "wechat")

    def test_convert_url_dispatches_cnblogs(self) -> None:
        with patch("blog2md.site_router.convert_cnblogs_url") as cnblogs_mock:
            cnblogs_mock.return_value = object()
            convert_url_to_md(url="https://www.cnblogs.com/a/p/1.html", output=Path("a.md"))
            cnblogs_mock.assert_called_once()

    def test_convert_url_dispatches_wechat(self) -> None:
        with patch("blog2md.site_router.convert_wechat_url") as wechat_mock:
            wechat_mock.return_value = object()
            convert_url_to_md(url="https://mp.weixin.qq.com/s/abc", output=Path("b.md"))
            wechat_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()


