import unittest

from backend.softcopyright.errors import sanitize_error_message


class ErrorSanitizationTests(unittest.TestCase):
    def test_connection_pool_host_and_relative_model_path_are_hidden(self):
        source = (
            "HTTPSConnectionPool(host='qiuqiutoken.com', port=443): Max retries exceeded "
            "with url: /v1/chat/completions (Caused by SSLError(SSLEOFError(8, 'EOF occurred')))"
        )

        sanitized = sanitize_error_message(source)

        self.assertNotIn("qiuqiutoken.com", sanitized)
        self.assertNotIn("/v1/chat/completions", sanitized)
        self.assertIn("模型网关连接", sanitized)
        self.assertIn("[模型接口]", sanitized)


if __name__ == "__main__":
    unittest.main()
