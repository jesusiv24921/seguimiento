import base64
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from werkzeug.exceptions import Forbidden

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

class PersonalAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {"SEGUIMIENTO_AUTH_USER": "test-user", "SEGUIMIENTO_AUTH_PASSWORD": "test-password"}):
            import app
        cls.module = app
        cls.headers = {"Authorization": "Basic " + base64.b64encode(b"test-user:test-password").decode()}

    def setUp(self):
        self.client = self.module.server.test_client()

    def test_global_login_still_required(self):
        for path in ("/personal", "/personal/access", "/_dash-layout"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/_dash-update-component", json={"output": "per-confirm.displayed", "inputs": []}).status_code, 401)

    def test_personal_opens_without_second_password(self):
        self.assertEqual(self.client.get("/personal", headers=self.headers).status_code, 200)
        import pages.personal as page
        with self.module.server.test_request_context("/personal"):
            layout = str(page.layout())
            self.assertIn("per-data", layout)
            self.assertNotIn("per-session-check", layout)
            self.assertNotIn("/personal/access", layout)

    def test_old_links_redirect(self):
        for path in ("/personal/access", "/personal/lock"):
            response = self.client.get(path, headers=self.headers)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["Location"], "/personal")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_cross_origin_write_blocked(self):
        import personal_auth
        callback = personal_auth.require_access(lambda: "ok")
        with self.module.server.test_request_context("/", method="POST", headers={"Origin": "https://other.example"}):
            with self.assertRaises(Forbidden):
                callback()
        with self.module.server.test_request_context("/", method="POST", headers={"Origin": "http://localhost"}):
            self.assertEqual(callback(), "ok")

    def test_payment_table_keeps_future_payment_visible_in_other_month(self):
        from datetime import date
        import personal as finance
        import pages.personal as page
        data = finance.empty()
        data["deudas"] = [dict(id="debt-123456", nombre="Compra A", entidad="Banco", saldo_inicial=1000000,
                               saldo_actual=500000, fecha_inicio="2026-10-01")]
        data["movimientos"] = [dict(id="payment", fecha="2026-11-01", deuda="debt-123456",
                                    tipo_movimiento="Abono dirigido a capital", valor=500000, capital=500000, observaciones="Prueba")]
        with patch.object(finance, "today", return_value=date(2026, 10, 4)), self.module.server.test_request_context("/personal"):
            result = page.render_table(data, "movimientos", 2026, 10)
            self.assertEqual(len(result.data), 1)
            self.assertEqual(result.data[0]["id"], "payment")
            self.assertIn("Compra A", result.data[0]["deuda"])
            self.assertEqual(result.data[0]["fecha_estado"], "Fecha futura")
            debts = page.render_table(data, "deudas", 2026, 10)
            self.assertEqual(debts.data[0]["saldo_actual"], 1000000)
            self.assertEqual(debts.data[0]["saldo_registrado"], 500000)
            self.assertIsNone(page.render_debt_plan(data, "movimientos")[0])
            self.assertEqual(data["movimientos"][0]["deuda"], "debt-123456")

if __name__ == "__main__":
    unittest.main()
