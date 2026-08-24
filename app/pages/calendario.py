"""Calendario — vista mensual de actividades por día, con festivos colombianos."""
from __future__ import annotations

import calendar as calendar_mod
from datetime import date

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dcc, html

import data as data_mod
from components import badge_estado, chart_card, page_header
from data_store import apply_all_filters, df_from_store
from theme import COLOR_PROYECTO_BRAND, DIAS_ES, INK_MUTED, MESES_ES, color_map, fmt_fecha_es

dash.register_page(__name__, path="/calendario", name="Calendario", title="Calendario")

layout = html.Div(className="page", children=[
    page_header("Calendario", "Actividades realizadas cada día, mes a mes.", period_id="page-header-period"),

    chart_card(dcc.Loading(type="circle", children=html.Div(id="cal-hero"))),

    dbc.Row([
        dbc.Col(chart_card([
            dbc.Row([
                dbc.Col(dbc.Button(html.I(className="bi bi-chevron-left"), id="btn-cal-prev",
                                     className="btn-cal-nav"), width="auto"),
                dbc.Col(html.Div(id="cal-month-label", className="cal-month-label"), width="auto"),
                dbc.Col(dbc.Button(html.I(className="bi bi-chevron-right"), id="btn-cal-next",
                                     className="btn-cal-nav"), width="auto"),
                dbc.Col(dbc.Button("Hoy", id="btn-cal-today", className="btn-cal-today", size="sm"),
                         width="auto", className="ms-auto"),
            ], className="align-items-center mb-3 g-2"),
            dcc.Loading(type="circle", children=html.Div(id="cal-grid")),
        ]), lg=8, className="mb-3"),
        dbc.Col(chart_card(html.Div(id="cal-day-detail"), className="cal-detail-card"), lg=4, className="mb-3"),
    ], className="g-3"),

    dcc.Store(id="store-cal-month", data=date.today().strftime("%Y-%m")),
    dcc.Store(id="store-cal-selected-day"),
])


@dash.callback(
    Output("store-cal-month", "data"),
    Input("btn-cal-prev", "n_clicks"),
    Input("btn-cal-next", "n_clicks"),
    Input("btn-cal-today", "n_clicks"),
    State("store-cal-month", "data"),
    prevent_initial_call=True,
)
def change_cal_month(_prev, _next, _today, current):
    trigger = dash.ctx.triggered_id
    period = pd.Period(current, freq="M") if current else pd.Period(date.today(), freq="M")
    if trigger == "btn-cal-prev":
        period = period - 1
    elif trigger == "btn-cal-next":
        period = period + 1
    elif trigger == "btn-cal-today":
        period = pd.Period(date.today(), freq="M")
    return str(period)


@dash.callback(
    Output("store-selected-activity", "data", allow_duplicate=True),
    Input({"type": "cal-activity", "id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_cal_activity(_all_clicks):
    triggered = dash.ctx.triggered_id
    if not triggered or not any(c for c in (_all_clicks or [])):
        return dash.no_update
    return triggered["id"]


@dash.callback(
    Output("store-cal-selected-day", "data"),
    Input({"type": "cal-day", "date": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def select_cal_day(_all_clicks):
    triggered = dash.ctx.triggered_id
    if not triggered or not any(c for c in (_all_clicks or [])):
        return dash.no_update
    return triggered["date"]


@dash.callback(
    Output("cal-hero", "children"),
    Output("cal-month-label", "children"),
    Output("cal-grid", "children"),
    Output("cal-day-detail", "children"),
    Input("store-data", "data"),
    Input("store-cal-month", "data"),
    Input("store-cal-selected-day", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_calendar(store_json, cal_month, selected_day, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        return html.Div("Sin datos disponibles.", className="section-caption"), "—", html.Div(), html.Div()

    filtered = apply_all_filters(df, start_date, end_date)

    # ---- Hero: días hábiles trabajados (tenure global, no depende de los filtros) ----
    fecha_ingreso = df["fecha_inicio"].min().date()
    hoy = date.today()
    n_dias, festivos_excluidos = data_mod.business_days_worked(fecha_ingreso, hoy)
    dias_habiles_totales = {d.date() for d in pd.bdate_range(fecha_ingreso, hoy)}
    total_calendar_days = (hoy - fecha_ingreso).days + 1
    weekend_days = total_calendar_days - len(dias_habiles_totales)
    hero = html.Div(className="cal-hero", children=[
        html.Div(html.I(className="bi bi-briefcase"), className="cal-hero-icon"),
        html.Div([
            html.Div([html.Span(f"{n_dias}", className="cal-hero-number"), "días hábiles trabajados"],
                      className="cal-hero-title"),
            html.Div(f"Desde el {fmt_fecha_es(fecha_ingreso)} hasta hoy ({fmt_fecha_es(hoy)}) · "
                     f"{weekend_days} días de fin de semana y {len(festivos_excluidos)} festivos "
                     f"colombianos excluidos", className="cal-hero-caption"),
        ]),
    ])

    # ---- Grid del mes ----
    period = pd.Period(cal_month, freq="M") if cal_month else pd.Period(hoy, freq="M")
    year, month = period.year, period.month
    festivos_mes = data_mod.colombia_holidays(year, year)
    weeks = calendar_mod.Calendar(firstweekday=0).monthdatescalendar(year, month)

    valid = filtered.dropna(subset=["fecha"])
    by_day: dict[date, pd.DataFrame] = {d: g for d, g in valid.groupby(valid["fecha"].dt.date)}

    day_cells = []
    for week in weeks:
        for d in week:
            in_month = d.month == month
            is_weekend = d.weekday() >= 5
            is_holiday = d in festivos_mes
            is_today = d == hoy
            is_selected = bool(selected_day) and d.isoformat() == selected_day
            acts = by_day.get(d)
            n_acts = 0 if acts is None else len(acts)
            horas_dia = 0.0 if acts is None else acts["horas"].fillna(0).sum()

            classes = ["cal-day"]
            if not in_month:
                classes.append("cal-day-out")
            if is_weekend:
                classes.append("cal-day-weekend")
            if is_holiday:
                classes.append("cal-day-holiday")
            if is_today:
                classes.append("cal-day-today")
            if is_selected:
                classes.append("cal-day-selected")
            if n_acts:
                classes.append("cal-day-has-activity")

            cell_children = [html.Div(str(d.day), className="cal-day-number")]
            if is_holiday and in_month:
                cell_children.append(html.Div(festivos_mes[d], className="cal-day-holiday-label"))
            if n_acts:
                proyectos_dia = acts["proyecto"].unique().tolist()
                color_map_dia = color_map(proyectos_dia, COLOR_PROYECTO_BRAND)
                dots = [html.Span(className="cal-dot", style={"backgroundColor": color_map_dia[p]})
                        for p in proyectos_dia[:5]]
                cell_children.append(html.Div(dots, className="cal-day-dots"))
                cell_children.append(html.Div(f"{horas_dia:.1f} h", className="cal-day-hours"))

            day_cells.append(html.Div(
                cell_children,
                id={"type": "cal-day", "date": d.isoformat()},
                className=" ".join(classes),
                n_clicks=0,
            ))

    grid = html.Div([
        html.Div([html.Div(lbl, className="cal-weekday-label") for lbl in DIAS_ES], className="cal-weekday-row"),
        html.Div(day_cells, className="cal-days-grid"),
    ])
    month_label = f"{MESES_ES[month].capitalize()} {year}"

    # ---- Panel de detalle del día seleccionado ----
    detail_date = None
    if selected_day:
        try:
            detail_date = date.fromisoformat(selected_day)
        except ValueError:
            detail_date = None
    if detail_date is None and year == hoy.year and month == hoy.month:
        detail_date = hoy

    if detail_date is None:
        detail = html.Div([html.I(className="bi bi-hand-index-thumb"),
                             " Selecciona un día del calendario para ver el detalle."], className="section-caption")
    else:
        tags = []
        if detail_date in festivos_mes:
            tags.append(f"Festivo: {festivos_mes[detail_date]}")
        if detail_date.weekday() >= 5:
            tags.append("Fin de semana")
        header = html.Div([html.I(className="bi bi-calendar-event"),
                             f" {fmt_fecha_es(detail_date)}" + (" · " + " · ".join(tags) if tags else "")],
                            className="section-title")

        acts = by_day.get(detail_date)
        if acts is None or acts.empty:
            body = html.Div("No hay actividades registradas este día.", className="section-caption")
        else:
            rows = []
            for _, r in acts.sort_values("inicio_dt").iterrows():
                horas_r = 0.0 if pd.isna(r["horas"]) else r["horas"]
                rows.append(html.Div(
                    id={"type": "cal-activity", "id": r["actividad_id"]},
                    className="cal-detail-row cal-detail-row-clickable", n_clicks=0,
                    children=[
                        html.Div(className="cal-detail-dot",
                                  style={"backgroundColor": COLOR_PROYECTO_BRAND.get(r["proyecto"], INK_MUTED)}),
                        html.Div([
                            html.Div(r["actividad"], className="cal-detail-title"),
                            html.Div(f"{r['proyecto']} · {r['tipo_actividad']} · {horas_r:.1f} h",
                                      className="cal-detail-meta"),
                        ], className="cal-detail-body"),
                        badge_estado(r["estado"]),
                        html.I(className="bi bi-chevron-right cal-detail-chevron"),
                    ],
                ))
            body = html.Div(rows, className="cal-detail-list")
        detail = html.Div([header, body])

    return hero, month_label, grid, detail
