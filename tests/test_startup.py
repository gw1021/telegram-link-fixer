import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def run_python(self, code):
        env = os.environ.copy()
        env.pop("BOT_TOKEN", None)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )

    def test_import_needs_no_token_and_does_not_configure_logging(self):
        result = self.run_python(
            "import logging; before = (logging.root.level, list(logging.root.handlers)); "
            "import link_fixer_bot; "
            "assert before == (logging.root.level, list(logging.root.handlers)); print('ok')"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")
        self.assertEqual(result.stderr, "")

    def test_start_without_token_fails_with_clear_message(self):
        result = self.run_python("from link_fixer_bot import main; main()")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BOT_TOKEN 환경변수를 설정하세요", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_http_requests_are_quiet_and_exception_tokens_are_redacted(self):
        result = self.run_python("""
import logging
from link_fixer_bot import configure_logging
token = '123456:fake-token-for-log-test'
configure_logging(token)
logging.getLogger('httpx').info('request should be hidden')
logging.getLogger('httpcore').info('request should be hidden')
try:
    raise ValueError('https://api.telegram.org/bot' + token + '/getMe')
except ValueError:
    logging.getLogger('linkfixer').exception('failed %s', token)
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("123456:fake-token-for-log-test", result.stderr)
        self.assertNotIn("request should be hidden", result.stderr)
        self.assertIn("<redacted>", result.stderr)
        self.assertIn("ValueError", result.stderr)


if __name__ == "__main__":
    unittest.main()
