from flask_backend.utils.mobile import is_mobile_user_agent

IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)
ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Mobile Safari/537.36"
)
DESKTOP_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DESKTOP_SAFARI_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
)


class TestIsMobileUserAgent:
    def test_detects_iphone(self):
        assert is_mobile_user_agent(IPHONE_UA) is True

    def test_detects_android(self):
        assert is_mobile_user_agent(ANDROID_UA) is True

    def test_rejects_desktop_chrome(self):
        assert is_mobile_user_agent(DESKTOP_CHROME_UA) is False

    def test_rejects_desktop_safari(self):
        assert is_mobile_user_agent(DESKTOP_SAFARI_UA) is False

    def test_rejects_empty_string(self):
        assert is_mobile_user_agent("") is False
