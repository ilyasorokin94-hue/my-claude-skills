"""Offline tests: no network, no real keys. Run: python3 -m unittest discover -s scripts/tests"""
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gsc  # noqa: E402


def make_sa(tmp):
    key = os.path.join(tmp, "k.pem")
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                    "-out", key], check=True, capture_output=True)
    pub = os.path.join(tmp, "p.pem")
    subprocess.run(["openssl", "pkey", "-in", key, "-pubout", "-out", pub], check=True, capture_output=True)
    with open(key) as fh:
        pem = fh.read()
    return {"type": "service_account", "client_email": "x@p.iam.gserviceaccount.com",
            "private_key": pem, "private_key_id": "abc", "project_id": "p",
            "token_uri": "https://oauth2.googleapis.com/token"}, pub


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sa, self.pub = make_sa(self.tmp)

    def test_jwt_signature_verifies(self):
        jwt = gsc.build_jwt(self.sa, gsc.SCOPE_RO, now=1000)
        h, c, sig = jwt.split(".")
        claims = json.loads(b64d(c))
        self.assertEqual(claims["iss"], self.sa["client_email"])
        self.assertEqual(claims["exp"], 4600)
        self.assertEqual(json.loads(b64d(h))["alg"], "RS256")
        sigf = os.path.join(self.tmp, "sig")
        with open(sigf, "wb") as fh:
            fh.write(b64d(sig))
        r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", self.pub, "-signature", sigf],
                           input=(h + "." + c).encode(), capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_key_from_env_raw_and_base64(self):
        raw = json.dumps(self.sa)
        for val in (raw, base64.b64encode(raw.encode()).decode()):
            with mock.patch.dict(os.environ, {"GSC_SERVICE_ACCOUNT_JSON": val}):
                self.assertEqual(gsc.load_service_account()["client_email"], self.sa["client_email"])

    def test_placeholder_and_bad_key(self):
        with mock.patch.dict(os.environ, {"GSC_SERVICE_ACCOUNT_JSON": "injected-by-proxy",
                                          "GSC_SERVICE_ACCOUNT_FILE": "/nonexistent"}):
            with self.assertRaises(gsc.GscError):
                gsc.load_service_account()
        with mock.patch.dict(os.environ, {"GSC_SERVICE_ACCOUNT_JSON": '{"type": "authorized_user"}'}):
            with self.assertRaisesRegex(gsc.GscError, "не ключ"):
                gsc.load_service_account()

    def test_no_temp_key_left(self):
        before = set(os.listdir(tempfile.gettempdir()))
        gsc.sign_rs256(b"x", self.sa["private_key"])
        leaked = [n for n in set(os.listdir(tempfile.gettempdir())) - before if n.startswith("gsc-")]
        self.assertEqual(leaked, [])


class SiteTests(unittest.TestCase):
    def test_resolve_prefers_domain_property(self):
        sites = [{"siteUrl": "https://dentalharmony.ru/"}, {"siteUrl": "sc-domain:dentalharmony.ru"}]
        with mock.patch.object(gsc, "list_sites", return_value=sites):
            self.assertEqual(gsc.resolve_site("https://www.dentalharmony.ru/x"), "sc-domain:dentalharmony.ru")
        with mock.patch.object(gsc, "list_sites", return_value=sites[:1]):
            self.assertEqual(gsc.resolve_site("dentalharmony.ru"), "https://dentalharmony.ru/")

    def test_resolve_unknown_site_errors(self):
        with mock.patch.object(gsc, "list_sites", return_value=[{"siteUrl": "sc-domain:a.ru"}]):
            with self.assertRaises(gsc.GscError):
                gsc.resolve_site("b.ru")


class PerfTests(unittest.TestCase):
    def test_perf_brand_split_and_hidden_share(self):
        def fake(method, url, body=None, scope=None):
            if not body.get("dimensions"):
                return {"rows": [{"clicks": 10, "impressions": 200, "ctr": 0.05, "position": 12.0}]}
            return {"rows": [
                {"keys": ["зубная гармония"], "clicks": 5, "impressions": 20, "ctr": 0.25, "position": 1.2},
                {"keys": ["имплантация балашиха"], "clicks": 1, "impressions": 90, "ctr": 0.01, "position": 18.0}]}
        tmp = tempfile.mkdtemp()
        with mock.patch.object(gsc, "gsc", side_effect=fake), \
                mock.patch.object(gsc, "CACHE_DIR", tmp), \
                mock.patch.object(gsc, "resolve_site", return_value="sc-domain:x.ru"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gsc.main(["perf", "--site", "x.ru", "--brand", "гармони"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Клики с видимыми запросами: 6 из 10 (60%)", out)
        self.assertIn("Бренд: клики 5, показы 20; небрендовые видимые: клики 1, показы 90", out)
        files = os.listdir(tmp)
        self.assertEqual(len(files), 1)
        with open(os.path.join(tmp, files[0])) as fh:
            self.assertIn("nonbrand", fh.read())

    def test_quickwins_filters_positions_and_brand(self):
        rows = {"rows": [
            {"keys": ["гармония"], "clicks": 0, "impressions": 50, "ctr": 0, "position": 5},
            {"keys": ["брекеты балашиха"], "clicks": 1, "impressions": 80, "ctr": 0.01, "position": 9},
            {"keys": ["виниры"], "clicks": 0, "impressions": 80, "ctr": 0, "position": 35}]}
        with mock.patch.object(gsc, "gsc", return_value=rows), \
                mock.patch.object(gsc, "CACHE_DIR", tempfile.mkdtemp()), \
                mock.patch.object(gsc, "resolve_site", return_value="sc-domain:x.ru"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                gsc.main(["quickwins", "--site", "x.ru", "--brand", "гармони"])
        out = buf.getvalue()
        self.assertIn(": 1", out.splitlines()[0])
        self.assertIn("брекеты балашиха", out)
        self.assertNotIn("виниры", out)


class PsiTests(unittest.TestCase):
    def test_shared_quota_message(self):
        err = gsc.GscHttpError(429, "Quota exceeded for consumer 'project_number:583797351490'")
        with mock.patch.object(gsc, "http_json", side_effect=err), \
                mock.patch.dict(os.environ, {"PSI_API_KEY": ""}):
            with self.assertRaisesRegex(gsc.GscError, "PSI_API_KEY"):
                gsc.psi_one("https://x.ru/", "mobile")

    def test_key_header(self):
        with mock.patch.dict(os.environ, {"PSI_API_KEY": "k1"}):
            self.assertEqual(gsc.google_key_headers(), {"X-Goog-Api-Key": "k1"})
        with mock.patch.dict(os.environ, {"PSI_API_KEY": "injected-by-proxy", "GOOGLE_API_KEY": ""}):
            self.assertEqual(gsc.google_key_headers(), {})


if __name__ == "__main__":
    unittest.main()
