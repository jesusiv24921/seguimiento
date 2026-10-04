from copy import deepcopy
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import personal as p


class DebtPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "personal.xlsx"
        clock = patch.object(p, "today", return_value=date(2026, 10, 4))
        clock.start()
        self.addCleanup(clock.stop)
        data = self.save("deudas", nombre="Compra", entidad="Banco", saldo_inicial=2000000,
                         fecha_inicio="2026-10-01", estado="Activa")
        self.debt = data["deudas"][0]["id"]

    def save(self, kind, **row):
        return p.mutate(kind, row, path=self.path)

    def plan(self, month="2026-11-01", **changes):
        return self.save("plan_deuda", **dict(dict(fecha=month, disponible_proyectado=1000000,
                         abono_extraordinario=500000, liquidez_minima=500000), **changes))

    def payment(self, amount=500000, when="2026-11-15", **changes):
        return self.save("movimientos", **dict(dict(fecha=when, deuda=self.debt,
                         tipo_movimiento="Abono dirigido a capital", valor=amount), **changes))

    def test_actual_cash_and_payments_have_one_source(self):
        self.plan()
        cat = self.save("categorias", nombre="Ingreso", tipo="Ingreso", estado="Activa")["categorias"][0]["id"]
        self.save("ingresos", fecha="2026-11-01", descripcion="Ingreso", categoria=cat,
                  valor_planeado=1000000, valor_real=1200000, estado="Recibido")
        self.payment(amount=50000, tipo_movimiento="Cuota normal", capital=30000)
        data = self.payment()
        report = p.debt_plan(data, "2026-11-20")
        row = report["rows"][0]
        self.assertEqual(row["disponible_real"], 1150000)
        self.assertEqual(row["liquidez_real"], 650000)
        self.assertEqual(row["liquidez_planeada"], 500000)
        self.assertEqual(row["diferencia_liquidez"], 150000)
        self.assertEqual(row["cumplimiento_pct"], 100)
        self.assertEqual(row["cumplimiento"], "CUMPLIDO")
        self.assertEqual(row["saldo_real"], 1470000)
        self.assertEqual(report["totals"]["abono_real"], 500000)
        self.assertEqual(report["abonos_realizados"], 500000)
        self.assertEqual(report["progreso"], 26.5)
        movement = data["movimientos"][-1]
        data = self.save("movimientos", **dict(movement, valor=250000))
        self.assertEqual(p.debt_plan(data, "2026-11-20")["rows"][0]["cumplimiento"], "PARCIAL")
        data = p.mutate("movimientos", delete_id=movement["id"], path=self.path)
        self.assertEqual(p.debt_plan(data, "2026-11-20")["totals"]["abono_real"], 0)

    def test_statuses_alerts_and_zero_scheduled(self):
        data = self.plan()
        self.assertEqual(p.debt_plan(data, "2026-11-20")["rows"][0]["cumplimiento"], "PENDIENTE")
        late = p.debt_plan(data, "2026-11-28")
        self.assertTrue(any("terminar" in a for a in late["alerts"]))
        self.assertTrue(any("mínimo" in a for a in late["alerts"]))
        self.assertTrue(any("saldo real" in a for a in late["alerts"]))
        self.assertEqual(p.debt_plan(data, "2026-12-01")["rows"][0]["cumplimiento"], "NO CUMPLIDO")
        data = self.payment(amount=100000)
        self.assertEqual(p.debt_plan(data, "2026-12-01")["rows"][0]["cumplimiento"], "PARCIAL")
        data = self.plan("2026-12-01", abono_extraordinario=0)
        row = p.debt_plan(data, "2026-12-01")["rows"][1]
        self.assertEqual(row["cumplimiento"], "Sin abono programado")
        self.assertIsNone(row["cumplimiento_pct"])

    def test_paid_off_and_nonnegative_debt(self):
        self.plan(abono_extraordinario=2500000)
        data = self.payment(amount=2000000)
        report = p.debt_plan(data, "2026-11-30")
        self.assertEqual(report["rows"][0]["cumplimiento"], "Deuda liquidada")
        self.assertEqual(report["rows"][0]["saldo_proyectado"], 0)
        self.assertEqual(report["progreso"], 100)
        self.assertTrue(any("supera" in a for a in report["alerts"]))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.payment(amount=1, when="2026-11-16")
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_edit_preserves_history_and_all_real_records(self):
        self.plan()
        self.plan("2027-01-01")
        data = self.payment()
        historical = p.debt_plan(data, "2026-12-01")["rows"][0]
        records = {key: deepcopy(value) for key, value in data.items() if key != "plan_deuda"}
        future = data["plan_deuda"][1]
        with patch.object(p, "today", return_value=date(2026, 12, 1)):
            updated = self.save("plan_deuda", **dict(future, disponible_proyectado=2000000, abono_extraordinario=750000))
            self.assertEqual(p.debt_plan(updated, "2026-12-01")["rows"][0], historical)
            self.assertEqual({k: v for k, v in updated.items() if k != "plan_deuda"}, records)
            with self.assertRaises(ValueError):
                self.save("plan_deuda", **dict(data["plan_deuda"][0], disponible_proyectado=1))
            with self.assertRaises(ValueError):
                p.mutate("plan_deuda", delete_id=data["plan_deuda"][0]["id"], path=self.path)
            updated = p.mutate("plan_deuda", delete_id=future["id"], path=self.path)
            self.assertEqual(p.debt_plan(updated, "2026-12-01")["rows"][0], historical)

    def test_current_month_cannot_be_deleted(self):
        data = self.plan("2026-10-01")
        with self.assertRaises(ValueError):
            p.mutate("plan_deuda", delete_id=data["plan_deuda"][0]["id"], path=self.path)

    def test_future_actuals_are_blank_and_future_payments_not_counted_today(self):
        self.plan()
        data = self.payment()
        report = p.debt_plan(data, "2026-10-04")
        self.assertIsNone(report["rows"][0]["abono_real"])
        self.assertIsNone(report["rows"][0]["saldo_real"])
        self.assertEqual(report["abonos_realizados"], 0)
        self.assertEqual(report["saldo_actual"], 2000000)

    def test_import_is_atomic_additive_and_totals_dynamic(self):
        before = p.load(self.path)
        csv = "fecha,disponible_proyectado,abono_extraordinario,liquidez_minima,observaciones\n2026-11-01,1000,400,600,Nota\n2027-01-01,2000,600,1400,Otra"
        rows = p.parse_debt_plan(csv)
        data = p.mutate("plan_deuda", batch=rows, expected=p.revision(before), path=self.path)
        self.assertEqual(data["deudas"], before["deudas"])
        totals = p.debt_plan(data)["totals"]
        self.assertEqual(totals["disponible_proyectado"], 3000)
        self.assertEqual(totals["abono_extraordinario"], 1000)
        self.assertEqual(totals["liquidez_planeada"], 2000)
        raw = self.path.read_bytes()
        with self.assertRaises(ValueError):
            p.mutate("plan_deuda", batch=rows, path=self.path)
        self.assertEqual(raw, self.path.read_bytes())
        with self.assertRaises(ValueError):
            p.mutate("plan_deuda", batch=[dict(rows[0], fecha="2027-02-01"), dict(rows[1], fecha="bad")], path=self.path)
        self.assertEqual(raw, self.path.read_bytes())
        with self.assertRaises(ValueError):
            p.mutate("plan_deuda", batch=[dict(rows[0], fecha="2027-02-01")], expected=p.revision(before), path=self.path)

    def test_old_workbook_load_does_not_write(self):
        wb = openpyxl.load_workbook(self.path)
        del wb["plan_deuda"]
        wb.save(self.path)
        wb.close()
        raw = self.path.read_bytes()
        self.assertEqual(p.load(self.path)["plan_deuda"], [])
        self.assertEqual(self.path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
