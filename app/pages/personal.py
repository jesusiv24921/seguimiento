"""Página Personal: dashboard, edición y proyección con componentes compartidos."""
from copy import deepcopy
import json
import dash
from dash import ALL, Input, Output, State, dcc, html, dash_table
from dash.dash_table.Format import Format, Group, Scheme, Symbol
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

import personal as finance
import personal_auth
from charts import base_layout
from components import page_header, chart_card
from theme import CAT_PALETTE, MESES_ES

dash.register_page(__name__, path="/personal", name="Personal", title="Personal · Finanzas")

LABELS = {"ingresos": "Ingresos", "gastos": "Gastos", "deudas": "Deudas",
          "movimientos": "Pagos y abonos", "proyecciones": "Proyección", "categorias": "Categorías"}
FIELD_LABELS = {"tasa_EA": "Tasa E.A. (%)", "capital": "Capital incluido en el pago",
                "saldo_inicial": "Saldo al inicio del registro", "saldo_actual": "Saldo actual (calculado)",
                "fecha_inicio": "Fecha del saldo inicial", "deuda": "Deuda",
                "ejecucion": "% ejecución", "fecha": "Fecha", "padre": "Categoría principal (opcional)",
                "categoria": "Categoría", "descripcion": "Descripción"}
COP = Format(precision=0, scheme=Scheme.fixed, group=Group.yes,
             groups=3, group_delimiter=".", decimal_delimiter=",",
             symbol=Symbol.yes, symbol_prefix="$ ")


def label(key):
    return FIELD_LABELS.get(key, key.replace("_", " ").capitalize())


def table(rows, columns=None, **kwargs):
    columns = columns or (list(rows[0]) if rows else [])
    money = finance.MONEY | {"planeado", "real", "diferencia", "liquidez_restante", "saldo_proyectado"}
    return dash_table.DataTable(
        data=rows, columns=[dict(name=label(c), id=c, **({"type": "numeric", "format": COP} if c in money else {})) for c in columns if c != "id"],
        sort_action="native", page_size=12, style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "inherit", "textAlign": "left", "minWidth": "110px", "maxWidth": "240px",
                    "whiteSpace": "normal", "padding": "10px", "fontSize": "13px"},
        style_header={"fontWeight": "600", "backgroundColor": "#f8f7f4"},
        style_data_conditional=[
            {"if": {"filter_query": "{diferencia} < 0", "column_id": "diferencia"}, "color": "#a52323"},
            {"if": {"filter_query": "{diferencia} > 0", "column_id": "diferencia"}, "color": "#0a6b0a"}],
        **kwargs)


def layout():
    current = finance.today()
    return html.Div(className="page personal-page", children=[
        page_header("Personal", "Finanzas por mes · Valores en pesos colombianos"),
        dcc.Store(id="per-data"), dcc.Store(id="per-edit-id"),
        html.Div(className="personal-period", children=[
            html.Div([html.Label("Año", htmlFor="per-year"), dbc.Input(id="per-year", type="number", min=1900, max=9998, step=1, value=current.year)]),
            html.Div([html.Label("Mes", htmlFor="per-month"), dcc.Dropdown(id="per-month", clearable=False, value=current.month,
                options=[{"label": MESES_ES[m].capitalize(), "value": m} for m in range(1, 13)])]),
            dbc.Button("Recargar", id="per-refresh", color="secondary", outline=True),
        ]),
        html.Div(id="per-message", role="status"),
        html.Div(id="per-dashboard"),
        chart_card([
            html.H2("Registros", className="section-title"),
            html.P("Selecciona una fila para editarla o eliminarla. Usa Nuevo para agregar un registro.", className="section-caption"),
            dcc.Tabs(id="per-kind", value="gastos", children=[dcc.Tab(label=v, value=k) for k, v in LABELS.items()]),
            html.Div(table([], finance.SCHEMAS["gastos"], id="per-records", row_selectable="single", selected_rows=[], selected_row_ids=[]), id="per-table", className="mt-3"),
            dbc.Button("Nuevo registro", id="per-new", className="my-3", outline=True),
            html.H3(id="per-form-title", className="section-title"),
            html.Div(id="per-fields", className="personal-form"),
            html.P("Gestiona tus categorías en la pestaña Categorías. Puedes renombrarlas, crear subcategorías o cambiar su estado a Inactiva. "
                   "Al desactivar una categoría principal, sus subcategorías también dejan de ofrecerse en registros nuevos. "
                   "El histórico conserva sus asociaciones; muestra el nombre actualizado.", className="section-caption"),
            html.Div(id="per-preview", role="status", className="my-2"),
            html.Div(className="d-flex gap-2 mt-3", children=[
                dbc.Button("Guardar", id="per-save", color="primary"),
                dbc.Button("Eliminar seleccionado", id="per-delete", color="danger", outline=True),
            ]),
            dcc.ConfirmDialog(id="per-confirm", message="¿Eliminar este registro? Se recalcularán los saldos y totales."),
            html.P("Los pagos registrados en Deudas ya se descuentan de la liquidez: no los repitas como gastos. "
                   "Un gasto de tipo Deuda es un gasto manual sin efecto sobre el saldo de una obligación.", className="section-caption mt-3"),
        ]),
        html.Div(id="per-history", className="mt-3"),
    ])


@dash.callback(Output("per-data", "data"), Output("per-message", "children"),
    Input("url", "pathname"), Input("per-refresh", "n_clicks"), Input("per-save", "n_clicks"), Input("per-confirm", "submit_n_clicks"),
    State("per-kind", "value"), State("per-edit-id", "data"), State("per-data", "data"),
    State({"type": "per-field", "name": ALL}, "value"), State({"type": "per-field", "name": ALL}, "id"),
    running=[(Output("per-save", "disabled"), True, False)])
@personal_auth.require_access
def load_or_save(pathname, refresh, save, delete, kind, record_id, data, values, ids):
    if pathname != "/personal":
        return dash.no_update, dash.no_update
    try:
        trigger = dash.ctx.triggered_id
        if trigger in ("per-save", "per-confirm"):
            if data is None:
                raise ValueError("Recarga los datos antes de guardar.")
            if trigger == "per-confirm" and not record_id:
                raise ValueError("Selecciona un registro para eliminar.")
            row = {i["name"]: v for i, v in zip(ids, values)}
            row["id"] = record_id
            updated = finance.mutate(kind, row=row, delete_id=record_id if trigger == "per-confirm" else None,
                                     expected=finance.revision(data))
            return updated, dbc.Alert("Registro eliminado." if trigger == "per-confirm" else "Cambios guardados.", color="success", duration=4000)
        return finance.load(), None
    except (ValueError, OSError) as exc:
        return dash.no_update, dbc.Alert(str(exc), color="danger")


@dash.callback(Output("per-confirm", "displayed"), Input("per-delete", "n_clicks"), State("per-edit-id", "data"), prevent_initial_call=True)
@personal_auth.require_access
def confirm_delete(clicks, record_id):
    return bool(clicks and record_id)


@dash.callback(Output("per-table", "children"), Input("per-data", "data"), Input("per-kind", "value"), Input("per-year", "value"), Input("per-month", "value"))
@personal_auth.require_access
def render_table(data, kind, year, month):
    data = data or finance.empty()
    rows = deepcopy(data[kind])
    if kind in ("ingresos", "gastos", "movimientos"):
        rows = [r for r in rows if r["fecha"][:7] == f"{int(year or 0):04d}-{int(month or 1):02d}"]
    if kind in ("ingresos", "gastos"):
        for r in rows:
            r["diferencia"] = (r["valor_planeado"] - r["valor_real"]) * (1 if kind == "gastos" else -1)
            r["categoria"] = finance.category_label(data, r["categoria"])
    if kind == "categorias":
        for r in rows:
            r["padre"] = finance.category_label(data, r["padre"]) if r["padre"] else "—"
    columns = finance.SCHEMAS[kind] + (["diferencia"] if kind in ("ingresos", "gastos") else [])
    return table(rows, columns, id="per-records", row_selectable="single", selected_rows=[], selected_row_ids=[])


def defaults(kind, year, month):
    result = {key: 0 if key in finance.MONEY or key in ("tasa_EA", "numero_cuotas", "cuotas_restantes") else "" for key in finance.SCHEMAS[kind]}
    result["fecha_inicio" if kind == "deudas" else "fecha"] = f"{int(year):04d}-{int(month):02d}-01"
    if kind in finance.STATES:
        result["estado"] = finance.STATES[kind][0]
    if kind == "gastos":
        result["tipo"] = "Variable"
    if kind == "categorias":
        result["tipo"] = "Gasto"
    if kind == "movimientos":
        result["tipo_movimiento"] = "Abono dirigido a capital"
    return result


@dash.callback(Output("per-fields", "children"), Output("per-edit-id", "data"), Output("per-form-title", "children"),
    Input("per-records", "selected_row_ids"), Input("per-kind", "value"), Input("per-new", "n_clicks"),
    Input("per-data", "data"), Input("per-year", "value"), Input("per-month", "value"))
@personal_auth.require_access
def editor(selected_ids, kind, new, data, year, month):
    data = data or finance.empty()
    selected = selected_ids[0] if selected_ids and dash.ctx.triggered_id == "per-records" else None
    record = next((r for r in data[kind] if r["id"] == selected), None)
    row = record or defaults(kind, year or finance.today().year, month or finance.today().month)
    fields = []
    for key in finance.SCHEMAS[kind]:
        if key == "id":
            continue
        options = None
        if key == "estado":
            options = finance.STATES[kind]
        elif key == "tipo":
            options = ["Ingreso", "Gasto"] if kind == "categorias" else ["Fijo", "Variable", "Deuda"]
        elif key == "categoria":
            options = finance.category_options(data, kind, row.get("categoria") if record else None)
        elif key == "padre":
            options = [{"label": "Sin categoría principal", "value": ""}] + [
                {"label": c["tipo"] + " · " + finance.category_label(data, c["id"]), "value": c["id"]}
                for c in data["categorias"] if c["id"] != selected]
        elif key == "tipo_movimiento":
            options = finance.MOVEMENTS
        elif key == "deuda":
            options = [{"label": f"{d['nombre']} · {d['entidad']} · {finance.cop(d['saldo_actual'])}", "value": d["id"]} for d in data["deudas"]]
        props = {"id": {"type": "per-field", "name": key}, "value": row.get(key)}
        if options is not None:
            field = dcc.Dropdown(**props, options=options, clearable=False)
        elif key == "observaciones":
            field = dbc.Textarea(**props)
        elif key in finance.MONEY or key in ("tasa_EA", "numero_cuotas", "cuotas_restantes"):
            field = dbc.Input(**props, type="number", min=0, step="any" if key == "tasa_EA" else 1, disabled=key == "saldo_actual")
        else:
            field = dbc.Input(**props, type="date" if key.startswith("fecha") else "text")
        hint = None
        if key == "categoria":
            hint = "Selecciona una categoría activa. Para crear o renombrar categorías, abre Categorías."
        if key == "capital":
            hint = "En Cuota normal u Otro, indica el capital amortizado. En Abono o Pago total se usa todo el valor. Interés aumenta la deuda sin salida de caja."
        if key == "cuotas_restantes":
            hint = "Actualización manual según el extracto; los abonos no recalculan las cuotas."
        fields.append(html.Div([html.Label(label(key), htmlFor=json.dumps(props["id"], sort_keys=True, separators=(",", ":"))), field, html.Small(hint, className="section-caption") if hint else None]))
    return fields, record["id"] if record else None, ("Editar " if record else "Agregar ") + LABELS[kind].lower()


@dash.callback(Output("per-preview", "children"), Input({"type": "per-field", "name": ALL}, "value"),
               State({"type": "per-field", "name": ALL}, "id"), State("per-kind", "value"))
@personal_auth.require_access
def preview(values, ids, kind):
    if kind != "proyecciones":
        return None
    row = {i["name"]: v for i, v in zip(ids, values)}
    try:
        remaining = finance.amount(row.get("disponible_proyectado")) - finance.amount(row.get("abono_extraordinario"))
        return dbc.Alert("Liquidez restante: " + finance.cop(remaining), color="warning" if remaining < 0 else "info")
    except ValueError as exc:
        return str(exc)


def card(title, rows):
    return chart_card([html.H3(title, className="section-title")] + [html.Div([html.Span(k), html.Strong(finance.cop(v))], className="personal-stat") for k, v in rows])


def graph(title, fig):
    base_layout(fig)
    fig.update_layout(colorway=CAT_PALETTE, separators=",.")
    fig.update_yaxes(tickprefix="$ ", tickformat=",.0f")
    return chart_card([html.H3(title, className="section-title"), dcc.Graph(figure=fig, style={"height": "340px"}, config={"displayModeBar": False, "responsive": True})])


@dash.callback(Output("per-dashboard", "children"), Output("per-history", "children"),
    Input("per-data", "data"), Input("per-year", "value"), Input("per-month", "value"))
@personal_auth.require_access
def dashboard(data, year, month):
    if data is None:
        return html.P("Cargando datos personales…"), None
    if not year or int(year) != year or not 1900 <= year <= 9998 or not month:
        return dbc.Alert("Selecciona un año válido entre 1900 y 9998 y un mes.", color="warning"), None
    year, month = int(year), int(month)
    s = finance.period(data, year, month)
    cards = [card(name, [("Planeados" if name != "Balance" else "Planeado", s[key + "_planeado"]),
                         ("Reales" if name != "Balance" else "Real", s[key + "_real"]), ("Diferencia", s[key + "_diferencia"])])
             for name, key in [("Ingresos", "ingresos"), ("Gastos", "gastos"), ("Balance", "balance")]]
    cards += [card("Liquidez", [("Disponible del mes", s["disponible"]), ("Acumulada", s["acumulada"])]),
              card("Deuda al cierre del mes", [("Saldo al comenzar el mes", s["saldo_inicial"]), ("Deudas incorporadas", s["nueva_deuda"]),
                   ("Pagos", s["pagos"]), ("Abonos extraordinarios", s["abonos"]), ("Saldo al cierre", s["saldo_actual"])])]
    grouped = finance.categories(data, year, month)
    comparison = go.Figure([go.Bar(name="Planeado", x=["Ingresos", "Gastos"], y=[s["ingresos_planeado"], s["gastos_planeado"]]),
                            go.Bar(name="Real", x=["Ingresos", "Gastos"], y=[s["ingresos_real"], s["gastos_real"]])])
    distribution = go.Figure(go.Bar(x=[r["categoria"] for r in grouped], y=[r["real"] for r in grouped], name="Gasto real"))
    top = [html.Div(cards, className="personal-cards"),
           html.P("Liquidez acumulada = ingresos registrados − gastos − pagos de deudas, desde el primer registro. "
                  "No incluye un saldo bancario anterior. Las diferencias positivas indican una mejora frente al plan.", className="section-caption"),
           html.Details(open=True, children=[html.Summary("Planeado vs real"), chart_card([
               table(grouped, ["categoria", "planeado", "real", "diferencia", "ejecucion"]),
               html.P("Diferencia de gastos = planeado − real. % vacío: presupuesto cero.", className="section-caption")]),
               html.Div([graph("Ingresos y gastos", comparison), graph("Gastos por categoría", distribution)], className="personal-charts")])]
    annual = finance.period(data, year)
    months = [finance.period(data, year, m) for m in range(1, 13)]
    names = [MESES_ES[m].capitalize() for m in range(1, 13)]
    evolution = go.Figure([go.Scatter(name=name, x=names, y=[r[key] for r in months], mode="lines+markers")
        for name, key in [("Ingresos", "ingresos_real"), ("Gastos", "gastos_real"), ("Balance", "balance_real")]])
    debt = go.Figure([go.Scatter(name=name, x=names, y=[r[key] for r in months], mode="lines+markers")
        for name, key in [("Saldo inicial del mes", "saldo_inicial"), ("Saldo al cierre", "saldo_actual")]])
    history = [html.Details(children=[html.Summary(f"Histórico y resumen anual · {year}"),
        card("Totales del año", [("Ingresos", annual["ingresos_real"]), ("Gastos", annual["gastos_real"]), ("Balance", annual["balance_real"]),
            ("Abonos extraordinarios", annual["abonos"]), ("Reducción neta de deuda", annual["reduccion_deuda"]),
            ("Liquidez generada en el año", annual["disponible"]), ("Liquidez acumulada al cierre", annual["acumulada"])]),
        html.Div([graph("Evolución mensual", evolution), graph("Evolución de deuda", debt)], className="personal-charts"),
        table([{"mes": names[i], "ingresos": r["ingresos_real"], "gastos": r["gastos_real"], "balance": r["balance_real"], "liquidez_restante": r["disponible"]} for i, r in enumerate(months)])])]
    try:
        projected = finance.project(data)
        fig = go.Figure([go.Bar(name=name, x=[r["fecha"][:7] for r in projected], y=[r[key] for r in projected])
            for name, key in [("Disponible", "disponible_proyectado"), ("Abonos", "abono_extraordinario"), ("Restante", "liquidez_restante")]])
        history.append(html.Details(open=True, children=[html.Summary("Proyección de meses futuros"),
            html.P("Parte de la deuda registrada a hoy y descuenta los abonos proyectados. No estima intereses ni cuotas futuras. "
                   "Edita los meses desde Registros → Proyección. El disponible ya debe descontar las obligaciones ordinarias.", className="section-caption"),
            table(projected, ["fecha", "disponible_proyectado", "abono_extraordinario", "liquidez_restante", "saldo_proyectado"]), graph("Liquidez proyectada", fig)]))
    except ValueError as exc:
        history.append(dbc.Alert(str(exc) + " Ajusta la proyección guardada.", color="warning"))
    return top, history
