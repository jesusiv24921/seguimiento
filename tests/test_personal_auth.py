import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import personal_auth as auth


class PersonalAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoded = generate_password_hash("private-test-password")

    def setUp(self):
        self.env = patch.dict(os.environ, {"PERSONAL_PASSWORD_HASH": self.encoded,
                              "SEGUIMIENTO_AUTH_PASSWORD": "program-test-password", "RENDER": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        auth._attempts.clear()
        self.server = Flask(__name__)
        self.server.secret_key = "test-only-session-secret"
        auth.install(self.server)
        self.server.add_url_rule("/protected", "protected", auth.require_access(lambda: "private"), methods=["GET", "POST"])
        self.client = self.server.test_client()

    def token(self):
        response = self.client.get("/personal/access")
        return re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True)).group(1)

    def login(self, password="private-test-password"):
        return self.client.post("/personal/access", data={"csrf": self.token(), "password": password})

    def test_program_password_does_not_unlock_personal(self):
        self.assertEqual(self.login("program-test-password").status_code, 401)
        self.assertEqual(self.client.get("/protected").status_code, 403)

    def test_success_logout_and_no_cache(self):
        self.assertEqual(self.login().status_code, 303)
        self.assertEqual(self.client.get("/protected").status_code, 200)
        self.assertEqual(self.client.get("/personal/access").headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.post("/personal/lock", data={"csrf": self.token()}).status_code, 303)
        self.assertEqual(self.client.get("/protected").status_code, 403)

    def test_missing_config_fails_closed(self):
        with patch.dict(os.environ, {"PERSONAL_PASSWORD_HASH": ""}):
            page = self.client.get("/personal/access")
            self.assertIn("Falta configurar", page.get_data(as_text=True))
            self.assertNotIn('name="password"', page.get_data(as_text=True))
            self.assertEqual(self.client.get("/protected").status_code, 403)

    def test_expiry_and_password_rotation_revoke_access(self):
        self.login()
        with patch.object(auth.time, "time", return_value=10**12):
            self.assertEqual(self.client.get("/protected").status_code, 403)
        with patch.dict(os.environ, {"PERSONAL_PASSWORD_HASH": "changed"}):
            self.assertEqual(self.client.get("/protected").status_code, 403)

    def test_login_and_logout_require_csrf(self):
        self.assertEqual(self.client.post("/personal/access", data={"password": "private-test-password"}).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/personal/lock").status_code, 403)
        self.assertEqual(self.client.get("/protected").status_code, 200)

    def test_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.login("wrong").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_same_password_configuration_rejected(self):
        with patch.dict(os.environ, {"SEGUIMIENTO_AUTH_PASSWORD": "private-test-password"}):
            self.assertEqual(self.login().status_code, 401)

    def test_cross_origin_write_blocked(self):
        self.login()
        self.assertEqual(self.client.post("/protected", headers={"Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.post("/protected", headers={"Origin": "http://localhost"}).status_code, 200)

    def test_separate_browser_stays_locked(self):
        self.login()
        self.assertEqual(self.server.test_client().get("/protected").status_code, 403)

    def test_all_personal_dash_operations_are_guarded(self):
        with patch.dict(os.environ, {"SEGUIMIENTO_AUTH_USER": "", "SEGUIMIENTO_AUTH_PASSWORD": ""}):
            import app
        client = app.server.test_client()
        self.assertEqual(client.get("/_dash-layout").status_code, 200)
        checked = 0
        for key, spec in app.app.callback_map.items():
            callback = spec.get("callback")
            if not callback or callback.__module__ != "pages.personal" or callback.__name__ == "check_session":
                continue
            outputs = spec["output"]
            output_description = lambda o: {"id": o.component_id, "property": o.component_property}
            payload = {"output": key, "outputs": [output_description(o) for o in outputs] if isinstance(outputs, list) else output_description(outputs),
                       "inputs": [dict(i, value=None) for i in spec["inputs"]],
                       "state": [dict(i, value=None) for i in spec["state"]], "changedPropIds": []}
            with self.subTest(callback=callback.__name__):
                response = client.post("/_dash-update-component", json=payload)
                self.assertEqual(response.status_code, 403)
            checked += 1
        self.assertEqual(checked, 6)
        import pages.personal as page
        with app.server.test_request_context("/personal"):
            self.assertIn("Desbloquear Personal", str(page.layout()))
            self.assertNotIn("per-data", str(page.layout()))


if __name__ == "__main__":
    unittest.main()
