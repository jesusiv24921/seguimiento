import base64
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import data
from hallazgos_import import CSV_COLUMNS, template_csv, validate_hallazgos_csv


def upload(csv_text: str) -> str:
    return "data:text/csv;base64," + base64.b64encode(csv_text.encode("utf-8")).decode("ascii")


class HallazgosImportTests(unittest.TestCase):
    def test_template_contains_only_official_columns(self):
        self.assertEqual(template_csv().lstrip("\ufeff").strip(), ",".join(CSV_COLUMNS))

    def test_validates_and_normalizes_valid_row(self):
        csv_text = (
            ",".join(CSV_COLUMNS) + "\n"
            "abierto,25/08/2026,—,sentinel,engine.py,evaluate(),Descripción con ñ\n"
        )
        result = validate_hallazgos_csv(upload(csv_text), "hallazgos.csv", [], "Sentinel Alerts")

        self.assertIsNone(result["error"])
        row = result["rows"][0]
        self.assertTrue(row["valido"])
        self.assertEqual(row["Estado"], "Abierto")
        self.assertEqual(row["Fecha hallazgo"], "2026-08-25")
        self.assertIsNone(row["Fecha cierre"])

    def test_rejects_missing_columns_and_invalid_rows(self):
        missing = "Estado,Fecha hallazgo\nAbierto,25/08/2026\n"
        result = validate_hallazgos_csv(upload(missing), "hallazgos.csv", [], "Sentinel Alerts")
        self.assertIn("Columnas faltantes", result["error"])

        invalid = ",".join(CSV_COLUMNS) + "\nPendiente,2026-08-25,,m,s,f,d\n"
        result = validate_hallazgos_csv(upload(invalid), "hallazgos.csv", [], "Sentinel Alerts")
        self.assertFalse(result["rows"][0]["valido"])
        self.assertIn("Estado inválido", result["rows"][0]["detalle"])

    def test_marks_existing_exact_record_as_not_importable(self):
        csv_text = ",".join(CSV_COLUMNS) + "\nAbierto,25/08/2026,,motor,main.py,run(),Mismo texto\n"
        existing = [{"Proyecto": "Sentinel Alerts", "Motor": "MOTOR", "Script": "main.py",
                     "Función": "run()", "Descripción": "mismo   texto"}]
        result = validate_hallazgos_csv(upload(csv_text), "hallazgos.csv", existing, "Sentinel Alerts")

        self.assertTrue(result["rows"][0]["duplicado"])
        self.assertFalse(result["rows"][0]["valido"])

    def test_persists_closing_date_through_existing_add_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "seguimiento.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.title = data.HALLAZGOS_SHEET
            sheet.append(data.HALLAZGOS_COLUMNS)
            workbook.save(path)

            ok, _message = data.add_hallazgo(
                proyecto="Sentinel Alerts", motor="motor", script="engine.py", funcion="run()",
                descripcion="Cierre histórico", estado="Cerrado",
                fecha_hallazgo=date(2026, 8, 25), fecha_cierre=date(2026, 8, 26), path=path,
            )

            self.assertTrue(ok)
            saved = data.load_hallazgos(path).iloc[0]
            self.assertEqual(saved["Fecha cierre"].date().isoformat(), "2026-08-26")


if __name__ == "__main__":
    unittest.main()
