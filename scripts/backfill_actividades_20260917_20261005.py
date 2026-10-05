"""
Backfill único de actividades New Opps + Sentinel Alerts, 17/09/2026 → 05/10/2026.

Reutiliza data.add_actividad() (mismo mecanismo de ID y formato de celdas que
el formulario "Nueva actividad"). Por defecto corre en dry-run; --apply escribe.

Transacción: se respalda el Excel, se insertan las filas sobre una copia de
trabajo, se verifica la copia (filas previas intactas, nuevas filas presentes
una sola vez) y solo entonces se reemplaza el original con os.replace(). Si
algo falla, el original no se toca. Idempotente: la clave lógica
fecha + hora_inicio + hora_fin + proyecto + actividad se compara contra el
Excel antes de insertar; una segunda ejecución marca todo como
SKIPPED_ALREADY_EXISTS.

Uso (desde seguimiento/):
    python scripts/backfill_actividades_20260917_20261005.py              # dry-run
    python scripts/backfill_actividades_20260917_20261005.py --apply
    python scripts/backfill_actividades_20260917_20261005.py --verify
    ... --excel /var/data/seguimiento.xlsx   (por defecto: data.EXCEL_PATH,
                                               que respeta SEGUIMIENTO_EXCEL_PATH)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import re
import shutil
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import data as data_mod  # noqa: E402

MARCA = "Backfill 2026-09-17→2026-10-05"
RESULTADO = "Actividad completada (registro reconstruido desde calendario y trabajo realizado)"

BACKFILL_CSV = """\
Fecha,HoraInicio,HoraFin,Proyecto,Actividad,Tema,Estado,Prioridad
17/09/2026,08:00,09:00,New Opps,Revisión del workflow AS-IS de New Opportunities en WellPotential,Entendimiento del flujo,Completado,Alta
17/09/2026,12:00,14:00,New Opps,"Inventario de funciones, fuentes de datos y dependencias del cálculo de potencial",Arquitectura New Opps,Completado,Media
17/09/2026,14:00,15:00,New Opps,Documentación de supuestos y pendientes técnicos del workflow,Documentación y QA,Completado,Media
18/09/2026,08:00,09:00,New Opps,Revisión del procesamiento de oportunidades e intervalos candidatos,PIN e intervalos,Completado,Alta
18/09/2026,11:00,12:00,New Opps,Revisión de integración LAS y propiedades petrofísicas,LAS y petrofísica,Completado,Alta
18/09/2026,15:30,16:00,New Opps,Trazabilidad de entradas y salidas del flujo WellPotential,Trazabilidad,Completado,Media
18/09/2026,16:00,16:30,New Opps,Revisión WellPotential,Sesión técnica New Opps,Completado,Alta
21/09/2026,08:00,09:00,New Opps,"Revisión del flujo de Net Pay, área y OOIP",Net Pay y OOIP,Completado,Alta
21/09/2026,10:00,12:00,New Opps,Análisis de metodología Voronoi para asociación espacial de oportunidades,Voronoi,Completado,Alta
21/09/2026,14:30,16:00,New Opps,Revisión del flujo E2E y asociación de oportunidades,Flujo E2E,Completado,Alta
22/09/2026,08:00,09:00,New Opps,Validación del PIN y construcción de intervalos candidatos,PIN e intervalos,Completado,Alta
22/09/2026,10:00,11:00,New Opps,Revisión de master wells y productores requeridos por el flujo,Master Wells,Completado,Alta
22/09/2026,12:00,14:00,New Opps,Preparación y validación de información requerida para Voronoi,Voronoi y QA,Completado,Alta
22/09/2026,14:30,16:00,New Opps,New Opps - sesión de revisión y seguimiento,Seguimiento New Opps,Completado,Alta
23/09/2026,08:00,09:00,New Opps,Validación del flujo oportunidades a intervalos y LAS,Flujo E2E,Completado,Alta
23/09/2026,10:00,12:00,New Opps,Revisión de variables petrofísicas utilizadas para Net Pay,LAS y Net Pay,Completado,Alta
23/09/2026,14:00,16:00,New Opps,Identificación de casos no ejecutables y controles de calidad,QA New Opps,Completado,Alta
24/09/2026,08:00,09:00,New Opps,"Revisión de ecuaciones de Darcy, OOIP y EUR",Ecuaciones New Opps,Completado,Alta
24/09/2026,10:00,11:00,New Opps,Análisis de permeabilidad y propiedades requeridas para cálculo de potencial,Darcy,Completado,Alta
24/09/2026,14:00,16:00,New Opps,Revisión de supuestos metodológicos del cálculo de potencial,Metodología,Completado,Alta
24/09/2026,16:00,17:00,New Opps,Seguimiento técnico New Opps con Francesco,Seguimiento New Opps,Completado,Alta
25/09/2026,08:00,10:00,New Opps,Validación de la metodología BSW utilizada en New Opportunities,BSW,Completado,Alta
25/09/2026,10:00,12:00,New Opps,Desarrollo y validación del enfoque de RF sintético,RF sintético,Completado,Alta
25/09/2026,14:00,15:00,New Opps,Análisis BSW vs RF y revisión de limitaciones metodológicas,Validación RF,Completado,Alta
28/09/2026,08:00,09:00,New Opps,Revisión de metodología de curvas Kr para unidades de ANDINA,Curvas Kr,Completado,Alta
28/09/2026,10:00,12:00,New Opps,Validación de clasificación KABS-Rock Type y parámetros Corey,Kr y Rock Type,Completado,Alta
28/09/2026,14:00,16:00,New Opps,Preparación de integración de curvas Kr al flujo de potencial,Integración Kr,Completado,Alta
29/09/2026,08:00,09:00,New Opps,Desarrollo de revisión masiva por pozo e intervalo,Revisión batch,Completado,Alta
29/09/2026,10:00,12:00,New Opps,Ejecución batch del flujo New Opportunities,Batch New Opps,Completado,Alta
29/09/2026,14:00,16:00,New Opps,"Validación de resultados OOIP, RF, Darcy, Kr, BSW y Qo",QA resultados,Completado,Alta
30/09/2026,08:00,09:00,New Opps,Revisión de resultados de la corrida masiva,QA batch,Completado,Alta
30/09/2026,10:00,12:00,New Opps,Análisis del comportamiento de BSW y su impacto sobre Qo,BSW y Qo,Completado,Alta
30/09/2026,14:00,16:00,New Opps,"Evaluación de modelos CART, GLM, GAM y baseline para estimación de BSW",Modelado BSW,Completado,Alta
01/10/2026,08:00,09:00,New Opps,Consulta y validación de perforados desde OPENWORKS,Perforados,Completado,Alta
01/10/2026,10:00,12:00,New Opps,Integración de estados OPEN CLOSED y SQUEEZED al flujo,Apertura de pozo,Completado,Alta
01/10/2026,14:00,16:00,New Opps,Configuración de apertura para cálculo Kr BSW y Qo,Integración Kr-BSW,Completado,Alta
02/10/2026,08:00,09:00,New Opps,Integración de metodología Kr y BSW al flujo productivo,Integración E2E,Completado,Alta
02/10/2026,10:00,12:00,New Opps,Ejecución y revisión del procesamiento masivo de pozos ANDINA,Batch ANDINA,Completado,Alta
02/10/2026,14:00,16:00,New Opps,"Análisis de tiempos de ejecución, errores LAS y estados no ejecutables",Performance y QA,Completado,Alta
05/10/2026,08:00,09:00,New Opps,Revisión integral de la metodología actual de New Opportunities,Metodología,Completado,Alta
05/10/2026,10:00,12:00,New Opps,Revisión conceptual del modelo estático utilizado en New Opportunities,Modelo estático,Completado,Media
05/10/2026,15:00,16:00,New Opps,"Consolidación de avances, pendientes técnicos y próximos pasos",Seguimiento New Opps,Completado,Media
05/10/2026,16:00,16:45,New Opps,Actualización proyecto AT2605 New Opp WO,Seguimiento del proyecto,Completado,Alta
17/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
17/09/2026,11:00,12:00,Sentinel Alerts,Refactoring Sentinel | Reunión de seguimiento semanal,Actualización Sentinel,Completado,Media
18/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
18/09/2026,14:00,15:00,Sentinel Alerts,Sentinel,Seguimiento Sentinel,Completado,Media
21/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
21/09/2026,13:30,14:30,Sentinel Alerts,Update estado Sentinel LCI,Actualización Sentinel,Completado,Media
22/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
23/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
24/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
24/09/2026,11:00,12:00,Sentinel Alerts,Refactoring Sentinel | Reunión de seguimiento semanal,Actualización Sentinel,Completado,Media
28/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
29/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
30/09/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
01/10/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
02/10/2026,09:00,10:00,Sentinel Alerts,Refactoring Sentinel | Reunión de seguimiento,Actualización Sentinel,Completado,Media
05/10/2026,09:00,10:00,Sentinel Alerts,Sentinel Production Surveillance,Surveillance,Completado,Media
"""

PERIODO = (dt.date(2026, 9, 17), dt.date(2026, 10, 5))

# Tipo/categoría cuando el Excel no tiene ya una actividad con el mismo título
# en el mismo proyecto (en ese caso se copian los de la más reciente, para
# conservar el criterio histórico, p.ej. "Sentinel Production Surveillance").
# Reuniones -> T004/C010, igual que A024/A029/A030.
REUNIONES = {"Sentinel Production Surveillance", "Refactoring Sentinel | Reunión de seguimiento semanal",
             "Refactoring Sentinel | Reunión de seguimiento", "Sentinel", "Update estado Sentinel LCI",
             "Revisión WellPotential", "New Opps - sesión de revisión y seguimiento",
             "Seguimiento técnico New Opps con Francesco", "Actualización proyecto AT2605 New Opp WO"}
REGLAS_TIPO = [  # (prefijo del título, tipo_actividad_id, categoria_id)
    ("Documentación", "T007", "C008"),
    ("Consolidación", "T007", "C008"),
    ("Inventario", "T007", "C008"),
    ("Trazabilidad", "T002", "C002"),
    ("Consulta", "T002", "C002"),
    ("Preparación y validación", "T003", "C002"),
    ("Validación", "T003", "C004"),
    ("Identificación", "T003", "C011"),
    ("Desarrollo", "T001", "C007"),
    ("Integración", "T001", "C007"),
    ("Configuración", "T001", "C007"),
    ("Preparación", "T001", "C007"),
    ("Ejecución", "T001", "C006"),
    ("Evaluación", "T006", "C003"),
    ("Análisis", "T002", "C003"),
    ("Revisión", "T002", "C003"),
]


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().casefold()


def _hhmm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dt.time, dt.datetime)):
        return v.strftime("%H:%M")
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(v))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else str(v).strip()


def _fecha(v) -> dt.date | None:
    ts = data_mod._fix_date_cell(v)  # mismo parseo que load_data()
    return None if ts is None or ts != ts else ts.date()


def _horas(f) -> float:
    return (dt.datetime.combine(f["fecha"], f["hf"]) - dt.datetime.combine(f["fecha"], f["hi"])).seconds / 3600


def leer_backfill() -> list[dict]:
    filas = []
    for i, r in enumerate(csv.DictReader(io.StringIO(BACKFILL_CSV)), start=1):
        filas.append({
            "n": i, "fecha": dt.datetime.strptime(r["Fecha"], "%d/%m/%Y").date(),
            "hi": dt.datetime.strptime(r["HoraInicio"], "%H:%M").time(),
            "hf": dt.datetime.strptime(r["HoraFin"], "%H:%M").time(),
            "proyecto": r["Proyecto"].strip(), "actividad": r["Actividad"].strip(),
            "tema": r["Tema"].strip(), "estado": r["Estado"].strip(), "prioridad": r["Prioridad"].strip(),
        })
    return filas


def leer_excel(path: Path):
    """Snapshot de ACTIVIDADES (fila -> tupla de valores A:P) + catálogos."""
    wb = openpyxl.load_workbook(path)
    ws = wb[data_mod.ACTIVIDADES_SHEET]
    headers = [c.value for c in ws[1]]
    col = {n: headers.index(n) for n in data_mod.ACTIVIDADES_COLUMNS}
    filas = []
    for row in ws.iter_rows(min_row=2, max_col=len(data_mod.ACTIVIDADES_COLUMNS), values_only=True):
        if all(v is None for v in row):
            continue
        filas.append({n: row[col[n]] for n in data_mod.ACTIVIDADES_COLUMNS} | {"_raw": tuple(row)})
    proyectos = {r[1]: r[0] for r in wb["PROYECTOS"].iter_rows(min_row=2, max_col=2, values_only=True) if r[0]}
    tipos = {r[0] for r in wb["TIPOS_ACTIVIDAD"].iter_rows(min_row=2, max_col=1, values_only=True) if r[0]}
    cats = {r[0] for r in wb["CATEGORIAS"].iter_rows(min_row=2, max_col=1, values_only=True) if r[0]}
    return filas, proyectos, tipos, cats


def clave(fecha, hi, hf, proyecto_id, actividad):
    return (fecha, _hhmm(hi), _hhmm(hf), _norm(proyecto_id), _norm(actividad))


def tipo_categoria(f, proyecto_id, existentes):
    previas = [e for e in existentes
               if _norm(e["proyecto_id"]) == _norm(proyecto_id) and _norm(e["actividad"]) == _norm(f["actividad"])
               and e["tipo_actividad_id"]]
    if previas:
        e = previas[-1]
        return e["tipo_actividad_id"], e["categoria_id"], f"heredado de {e['actividad_id']}"
    if f["actividad"] in REUNIONES:
        return "T004", "C010", "regla reunión"
    for prefijo, t, c in REGLAS_TIPO:
        if f["actividad"].startswith(prefijo):
            return t, c, f"regla '{prefijo}'"
    return "T002", "C003", "regla por defecto"


def validar(filas, proyectos, tipos, cats) -> list[str]:
    errores = []
    festivos = data_mod.colombia_holidays(2026, 2026)
    vistos = set()
    for f in filas:
        tag = f"fila {f['n']} ({f['fecha']:%d/%m/%Y} {f['hi']:%H:%M})"
        if not (PERIODO[0] <= f["fecha"] <= PERIODO[1]):
            errores.append(f"{tag}: fuera del periodo")
        if f["fecha"].weekday() >= 5:
            errores.append(f"{tag}: cae en fin de semana")
        if f["fecha"] in festivos:
            errores.append(f"{tag}: festivo ({festivos[f['fecha']]})")
        if f["hf"] <= f["hi"]:
            errores.append(f"{tag}: hora_fin <= hora_inicio")
        if f["proyecto"] not in proyectos:
            errores.append(f"{tag}: proyecto '{f['proyecto']}' no existe en PROYECTOS")
        if f["estado"] not in data_mod.ESTADOS_VALIDOS.values():
            errores.append(f"{tag}: estado inválido")
        if f["prioridad"] not in data_mod.PRIORIDADES_VALIDAS.values():
            errores.append(f"{tag}: prioridad inválida")
        if "cancel" in f["actividad"].casefold():
            errores.append(f"{tag}: reunión cancelada")
        k = (f["fecha"], f["hi"], f["hf"], f["proyecto"], _norm(f["actividad"]))
        if k in vistos:
            errores.append(f"{tag}: duplicada dentro del backfill")
        vistos.add(k)
    # Solapes dentro del propio backfill (evita doble contabilización de horas)
    por_dia: dict[dt.date, list] = {}
    for f in filas:
        por_dia.setdefault(f["fecha"], []).append(f)
    for d, lst in por_dia.items():
        lst = sorted(lst, key=lambda x: x["hi"])
        for a, b in zip(lst, lst[1:]):
            if b["hi"] < a["hf"]:
                errores.append(f"{d:%d/%m/%Y}: solape '{a['actividad']}' {a['hi']:%H:%M}-{a['hf']:%H:%M} "
                               f"con '{b['actividad']}' {b['hi']:%H:%M}-{b['hf']:%H:%M}")
    return errores


def planificar(filas, existentes, proyectos, tipos, cats):
    claves_exist = {clave(_fecha(e["fecha_inicio"]), e["hora_inicio"], e["hora_fin"], e["proyecto_id"], e["actividad"]): e
                    for e in existentes}
    plan, avisos = [], []
    for f in sorted(filas, key=lambda x: (x["fecha"], x["hi"])):  # IDs en orden cronológico
        pid = proyectos[f["proyecto"]]
        k = clave(f["fecha"], f["hi"], f["hf"], pid, f["actividad"])
        if k in claves_exist:
            plan.append((f, "SKIPPED_ALREADY_EXISTS", claves_exist[k]["actividad_id"], None))
            continue
        t, c, origen = tipo_categoria(f, pid, existentes)
        if t not in tipos or (c and c not in cats):
            plan.append((f, "ERROR", f"tipo/categoría {t}/{c} no existe en catálogo", None))
            continue
        # Aviso (no bloquea): actividad existente que se solapa en horario ese día
        for e in existentes:
            if _fecha(e["fecha_inicio"]) == f["fecha"] and e["hora_inicio"] and e["hora_fin"]:
                if _hhmm(e["hora_inicio"]) < f"{f['hf']:%H:%M}" and f"{f['hi']:%H:%M}" < _hhmm(e["hora_fin"]):
                    avisos.append(f"{f['fecha']:%d/%m/%Y} {f['hi']:%H:%M}-{f['hf']:%H:%M} '{f['actividad']}' "
                                  f"se solapa con existente {e['actividad_id']} '{e['actividad']}'")
        plan.append((f, "INSERT", origen, (pid, t, c)))
    return plan, avisos


def insertar(path: Path, plan, existentes_snapshot):
    """Inserta sobre una copia de trabajo y la promueve solo si todo verifica."""
    mtime_original = path.stat().st_mtime_ns
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    work = path.with_name(f".{path.stem}_backfill_work_{stamp}{path.suffix}")
    shutil.copy2(path, work)
    resultados = []
    try:
        for f, accion, info, ids in plan:
            if accion != "INSERT":
                resultados.append((f, accion, info))
                continue
            pid, t, c = ids
            ok, msg = data_mod.add_actividad(
                fecha_inicio=f["fecha"], hora_inicio=f["hi"], hora_fin=f["hf"],
                proyecto_id=pid, tipo_actividad_id=t, categoria_id=c,
                actividad=f["actividad"], descripcion=f["actividad"], tema=f["tema"],
                resultado=RESULTADO, estado=f["estado"], prioridad=f["prioridad"],
                observaciones=MARCA, path=work)
            if not ok:
                raise RuntimeError(f"add_actividad falló en fila {f['n']}: {msg}")
            resultados.append((f, "INSERTED", re.search(r"A\d+", msg).group()))

        nuevas, _, _, _ = leer_excel(work)
        previas = [e["_raw"] for e in nuevas[:len(existentes_snapshot)]]
        if previas != [e["_raw"] for e in existentes_snapshot]:
            raise RuntimeError("Verificación fallida: filas previas cambiaron en la copia de trabajo")
        if path.stat().st_mtime_ns != mtime_original:
            raise RuntimeError("El Excel original cambió durante el backfill (¿edición desde la app?). Abortado.")
        os.replace(work, path)
    except Exception:
        work.unlink(missing_ok=True)
        raise
    return resultados, backup


def verificar(path: Path, filas, snapshot_ids=None) -> int:
    existentes, proyectos, _, _ = leer_excel(path)
    nombre_proy = {v: k for k, v in proyectos.items()}
    problemas = 0
    ids = [e["actividad_id"] for e in existentes]
    if len(ids) != len(set(ids)):
        print("  ✗ IDs duplicados en ACTIVIDADES"); problemas += 1
    claves = [clave(_fecha(e["fecha_inicio"]), e["hora_inicio"], e["hora_fin"], e["proyecto_id"], e["actividad"])
              for e in existentes]
    tabla, horas = [], {"New Opps": 0.0, "Sentinel Alerts": 0.0}
    for f in filas:
        k = clave(f["fecha"], f["hi"], f["hf"], proyectos[f["proyecto"]], f["actividad"])
        n = claves.count(k)
        if n != 1:
            print(f"  ✗ fila {f['n']} aparece {n} veces"); problemas += 1
            continue
        e = existentes[claves.index(k)]
        h = _horas(f)
        if (_fecha(e["fecha_inicio"]) != f["fecha"] or _fecha(e["fecha_fin"]) != f["fecha"]
                or nombre_proy.get(e["proyecto_id"]) != f["proyecto"] or e["estado"] != "Completado"
                or e["prioridad"] != f["prioridad"] or e["tema"] != f["tema"]):
            print(f"  ✗ {e['actividad_id']} con valores inesperados"); problemas += 1
        horas[f["proyecto"]] += h
        tabla.append((e["actividad_id"], f, h))
    canceladas = [e for e in existentes if "cancel" in _norm(e["actividad"])
                  and PERIODO[0] <= (_fecha(e["fecha_inicio"]) or dt.date.min) <= PERIODO[1]]
    if canceladas:
        print(f"  ✗ hay reuniones canceladas en el periodo: {[e['actividad_id'] for e in canceladas]}"); problemas += 1

    # Filas históricas vs el respaldo más reciente creado por --apply
    backups = sorted(path.parent.glob(f"{path.stem}_backup_*{path.suffix}"), key=lambda p: p.stat().st_mtime)
    if backups:
        previas, _, _, _ = leer_excel(backups[-1])
        intactas = [e["_raw"] for e in existentes[:len(previas)]] == [e["_raw"] for e in previas]
        print(f"  {'✓' if intactas else '✗'} backup {backups[-1].name}: {len(previas)} filas previas "
              f"{'idénticas' if intactas else 'MODIFICADAS'} en el Excel actual")
        problemas += 0 if intactas else 1
    else:
        print("  - sin backup de backfill junto al Excel (no se comparan filas históricas)")
    print(f"  {'✓' if len(ids) == len(set(ids)) else '✗'} IDs únicos ({len(ids)} actividades)   "
          f"{'✓' if not canceladas else '✗'} sin reuniones canceladas en el periodo")
    try:
        r = data_mod.load_data(path)
        print(f"  ✓ load_data(): {len(r['actividades'])} actividades, "
              f"{len([i for i in r['issues'] if i.get('actividad_id') in {t[0] for t in tabla}])} incidencias en filas del backfill")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ load_data() falló: {exc}"); problemas += 1
    print(f"  siguiente ID disponible: {data_mod.next_actividad_id(path)}")

    print("\nID | Fecha | Horario | Duración | Proyecto | Actividad | Tema | Estado | Prioridad")
    for aid, f, h in sorted(tabla, key=lambda x: (x[1]["fecha"], x[1]["hi"])):
        print(f"{aid} | {f['fecha']:%d/%m/%Y} | {f['hi']:%H:%M} — {f['hf']:%H:%M} | {h:.2f} h | {f['proyecto']} | "
              f"{f['actividad']} | {f['tema']} | Completado | {f['prioridad']}")
    print(f"\nHORAS_NEW_OPPS = {horas['New Opps']:.2f}   HORAS_SENTINEL = {horas['Sentinel Alerts']:.2f}   "
          f"TOTAL = {sum(horas.values()):.2f}")
    print("VERIFICACIÓN:", "OK" if problemas == 0 else f"{problemas} problema(s)")
    return problemas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--excel", type=Path, default=data_mod.EXCEL_PATH)
    ap.add_argument("--apply", action="store_true", help="escribir en el Excel (por defecto: dry-run)")
    ap.add_argument("--verify", action="store_true", help="solo verificar el estado final")
    args = ap.parse_args()
    path = args.excel.resolve()
    print(f"Excel: {path}")

    filas = leer_backfill()
    existentes, proyectos, tipos, cats = leer_excel(path)
    if args.verify:
        sys.exit(1 if verificar(path, filas) else 0)

    ultimo = max((e["actividad_id"] for e in existentes if e["actividad_id"]),
                 key=lambda s: int(re.search(r"\d+", str(s)).group()), default=None)
    fechas = [d for d in (_fecha(e["fecha_inicio"]) for e in existentes) if d]
    print(f"SEGUIMIENTO_EXCEL_PATH = {os.environ.get('SEGUIMIENTO_EXCEL_PATH') or '(no definida; se usa la copia del repo)'}")
    print(f"Actividades existentes: {len(existentes)}   último ID: {ultimo}   "
          f"siguiente (next_actividad_id): {data_mod.next_actividad_id(path)}   "
          f"actividad más reciente: {max(fechas).strftime('%d/%m/%Y') if fechas else '-'}")
    print(f"Filas de backfill: {len(filas)} "
          f"(New Opps={sum(f['proyecto'] == 'New Opps' for f in filas)}, "
          f"Sentinel={sum(f['proyecto'] == 'Sentinel Alerts' for f in filas)})")

    errores = validar(filas, proyectos, tipos, cats)
    if errores:
        print("\nVALIDACIÓN FALLIDA — no se escribe nada:")
        for e in errores:
            print("  -", e)
        sys.exit(2)
    print("Validación: OK (fechas hábiles, horarios, catálogos, sin canceladas, sin solapes internos)")

    plan, avisos = planificar(filas, existentes, proyectos, tipos, cats)
    for a in avisos:
        print("  AVISO solape con existente:", a)

    print("\nn | estado | fecha | horario | proyecto | actividad | tipo/cat (origen)")
    for f, accion, info, ids in plan:
        tc = f"{ids[1]}/{ids[2]} ({info})" if ids else info
        print(f"{f['n']:>2} | {accion} | {f['fecha']:%d/%m/%Y} | {f['hi']:%H:%M}-{f['hf']:%H:%M} | "
              f"{f['proyecto']} | {f['actividad']} | {tc}")

    if not args.apply:
        ins = [p[0] for p in plan if p[1] == "INSERT"]
        h = lambda proy: sum(_horas(f) for f in ins if f["proyecto"] == proy)
        n_no = sum(f["proyecto"] == "New Opps" for f in ins)
        n_se = sum(f["proyecto"] == "Sentinel Alerts" for f in ins)
        nxt = int(re.search(r"\d+", data_mod.next_actividad_id(path)).group())
        print("\n=== DRY-RUN (no se escribió nada) ===")
        print(f"NEW_OPPS_A_INSERTAR = {n_no}   HORAS = {h('New Opps'):.2f}")
        print(f"SENTINEL_A_INSERTAR = {n_se}   HORAS = {h('Sentinel Alerts'):.2f}")
        print(f"TOTAL_A_INSERTAR = {len(ins)}   HORAS = {h('New Opps') + h('Sentinel Alerts'):.2f}")
        print(f"OMITIDOS_POR_DUPLICADO = {sum(p[1] == 'SKIPPED_ALREADY_EXISTS' for p in plan)}   "
              f"ERRORES = {sum(p[1] == 'ERROR' for p in plan)}")
        print(f"SOLAPES_CON_EXISTENTES = {len(avisos)}" + (" (ver AVISO arriba)" if avisos else ""))
        if ins:
            print(f"RANGO_IDS_ESPERADO = A{nxt:03d} → A{nxt + len(ins) - 1:03d}")
        print(f"BACKUP_SE_CREARÁ_EN = {path.with_name(path.stem + '_backup_<YYYYMMDD_HHMMSS>' + path.suffix)}")
        print("Usa --apply para escribir.")
        return
    if any(p[1] == "ERROR" for p in plan):
        print("\nHay filas con ERROR — no se escribe nada."); sys.exit(2)
    if not any(p[1] == "INSERT" for p in plan):
        print(f"\nNada que insertar: OMITIDOS_POR_DUPLICADO = {len(plan)}   ERRORES = 0. El Excel no se modifica.")
        sys.exit(1 if verificar(path, filas) else 0)

    resultados, backup = insertar(path, plan, existentes)
    print(f"\nRespaldo: {backup}")
    for f, estado, info in resultados:
        print(f"  {estado:<24} fila {f['n']:>2} -> {info}")
    ins = [r for r in resultados if r[1] == "INSERTED"]
    horas = lambda proy: sum(_horas(f) for f, _, _ in ins if f["proyecto"] == proy)
    print(f"\nNEW_OPPS_INSERTADOS = {sum(f['proyecto'] == 'New Opps' for f, _, _ in ins)}   HORAS_NEW_OPPS = {horas('New Opps'):.2f}")
    print(f"SENTINEL_INSERTADOS = {sum(f['proyecto'] == 'Sentinel Alerts' for f, _, _ in ins)}   HORAS_SENTINEL = {horas('Sentinel Alerts'):.2f}")
    print(f"TOTAL_INSERTADOS = {len(ins)}   TOTAL_HORAS = {horas('New Opps') + horas('Sentinel Alerts'):.2f}")
    print(f"OMITIDOS_POR_DUPLICADO = {sum(r[1] == 'SKIPPED_ALREADY_EXISTS' for r in resultados)}   ERRORES = 0")
    print("\n--- Verificación post-inserción ---")
    sys.exit(1 if verificar(path, filas) else 0)


if __name__ == "__main__":
    main()
