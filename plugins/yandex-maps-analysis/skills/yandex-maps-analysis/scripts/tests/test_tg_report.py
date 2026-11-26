"""Тесты tg_report.py. Запуск: python -m unittest discover -s scripts/tests

Настоящий Telegram не трогаем: скрипт ходит на локальный сервер через TG_API_BASE.
"""
import io
import json
import os
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tg_report  # noqa: E402

TOKEN = "111111:TEST-TOKEN-NOT-REAL"

# Среду нельзя очищать целиком: на Windows без SYSTEMROOT и PATH OpenSSL не
# создаёт SSL-контекст, а `urlopen` строит его даже для адреса http://, и все
# три теста отправки падали с «нет связи с Telegram». Поэтому системные
# переменные оставляем, а настройки бота с самой машины убираем, чтобы тест
# не ушёл в настоящий чат.
SISTEMNYE_PEREMENNYE = (
    "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "COMSPEC",
    "TEMP", "TMP", "HOME", "LANG", "LC_ALL",
)


def sreda(**peremennye):
    osnova = {k: v for k, v in os.environ.items()
              if k.upper() in SISTEMNYE_PEREMENNYE}
    osnova.update(peremennye)
    return osnova


class FakeTelegram(BaseHTTPRequestHandler):
    calls = []
    fail = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        FakeTelegram.calls.append((self.path, body))
        if FakeTelegram.fail:
            payload, status = {"ok": False, "description": "Bad Request: chat not found"}, 400
        else:
            payload, status = {"ok": True, "result": {}}, 200
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class TgReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:{}".format(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeTelegram.calls = []
        FakeTelegram.fail = False

    def run_main(self, argv, text="", env=None):
        environ = sreda(TG_BOT_TOKEN=TOKEN, TG_CHAT_ID="-100123", TG_API_BASE=self.base)
        if env is not None:
            environ = sreda(**env)
        stdin = mock.Mock()
        stdin.buffer = io.BytesIO(text.encode("utf-8"))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch.object(sys, "stdin", stdin):
            with redirect_stdout(out), redirect_stderr(err):
                code = tg_report.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_sends_summary(self):
        code, out, _ = self.run_main([], "Отзывы, Яндекс Карты\n[Клиника А]: новых нет")
        self.assertEqual(code, 0)
        self.assertEqual(len(FakeTelegram.calls), 1)
        path, body = FakeTelegram.calls[0]
        self.assertEqual(path, "/bot{}/sendMessage".format(TOKEN))
        self.assertEqual(body["chat_id"], "-100123")
        self.assertIn("[Клиника А]: новых нет", body["text"])

    def test_missing_settings(self):
        code, _, err = self.run_main([], "текст", env={"TG_API_BASE": self.base})
        self.assertEqual(code, 2)
        self.assertIn("TG_BOT_TOKEN", err)
        self.assertEqual(FakeTelegram.calls, [])

    def test_empty_text(self):
        code, _, _ = self.run_main([], "   \n")
        self.assertEqual(code, 2)
        self.assertEqual(FakeTelegram.calls, [])

    def test_refuses_text_with_token(self):
        code, _, err = self.run_main([], "сводка {}".format(TOKEN))
        self.assertEqual(code, 2)
        self.assertNotIn(TOKEN, err)
        self.assertEqual(FakeTelegram.calls, [])

    def test_failure_hides_token(self):
        FakeTelegram.fail = True
        code, out, err = self.run_main([], "сводка")
        self.assertEqual(code, 3)
        self.assertIn("chat not found", err)
        self.assertNotIn(TOKEN, out + err)

    def test_no_connection(self):
        env = {"TG_BOT_TOKEN": TOKEN, "TG_CHAT_ID": "1", "TG_API_BASE": "http://127.0.0.1:9"}
        code, out, err = self.run_main([], "сводка", env=env)
        self.assertEqual(code, 3)
        self.assertNotIn(TOKEN, out + err)

    def test_long_text_is_split(self):
        text = "\n".join("[Клиника {}]: новых нет".format(i) for i in range(400))
        code, out, _ = self.run_main([], text)
        self.assertEqual(code, 0)
        self.assertGreater(len(FakeTelegram.calls), 1)
        for _, body in FakeTelegram.calls:
            self.assertLessEqual(len(body["text"]), tg_report.LIMIT)
        joined = "\n".join(body["text"] for _, body in FakeTelegram.calls)
        self.assertEqual(joined, text)

    def test_proverka_sends_nothing(self):
        code, out, _ = self.run_main(["--proverka"], "")
        self.assertEqual(code, 0)
        self.assertIn("TG_BOT_TOKEN: задан", out)
        self.assertNotIn(TOKEN, out)
        self.assertEqual(FakeTelegram.calls, [])


if __name__ == "__main__":
    unittest.main()
