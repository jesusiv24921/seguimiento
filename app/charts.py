"""
Funciones de gráficos reutilizables. Cada función recibe un DataFrame ya
filtrado (por la página que la llama) y devuelve una figura de Plotly lista
para un dcc.Graph. Mantener esto separado evita que Resumen y Análisis
dupliquen el mismo boilerplate de px.bar/px.pie con distinta granularidad.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import data as data_mod
from theme import (ACCENT, COLOR_ESTADO, COLOR_PROYECTO_BRAND, GRID, HALLAZGO_ESTADO_COLOR, INK_MUTED, INK_PRIMARY,
                    INK_SECONDARY, MESES_ES, SURFACE, color_map)


def _fmt_semana_es(inicio: pd.Timestamp) -> str:
    """'03–09 Ago' (o '29 Jul – 04 Ago' si la semana cruza de mes)."""
    fin = inicio + pd.Timedelta(days=6)
    if inicio.month == fin.month:
        return f"{inicio.day:02d}–{fin.day:02d} {MESES_ES[inicio.month][:3].capitalize()}"
    return (f"{inicio.day:02d} {MESES_ES[inicio.month][:3].capitalize()} – "
            f"{fin.day:02d} {MESES_ES[fin.month][:3].capitalize()}")


def empty_figure(message: str, height: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=INK_MUTED, size=13))
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE, height=height,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def base_layout(fig: go.Figure, height: int = 340, legend: bool = True) -> go.Figure:
    fig.update_layout(
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=INK_SECONDARY, family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", size=12),
        margin=dict(l=10, r=10, t=30, b=10),
        height=height,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                     font=dict(color=INK_SECONDARY)),
        hoverlabel=dict(bgcolor=SURFACE, font_color=INK_PRIMARY, bordercolor=GRID,
                         font_family="Inter, system-ui, sans-serif"),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=INK_MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=INK_MUTED))
    return fig


def fig_evolucion_semanal(df: pd.DataFrame, height: int = 320) -> go.Figure:
    """Horas por semana, apiladas por proyecto."""
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    cmap = color_map(df["proyecto"].unique().tolist(), COLOR_PROYECTO_BRAND)
    semanal = (df.groupby(["semana_inicio", "proyecto"], as_index=False)["horas"]
               .sum().sort_values("semana_inicio"))
    fig = px.bar(
        semanal, x="semana_inicio", y="horas", color="proyecto",
        color_discrete_map=cmap, category_orders={"proyecto": sorted(df["proyecto"].unique())},
        labels={"semana_inicio": "Semana", "horas": "Horas", "proyecto": "Proyecto"},
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(barmode="stack", bargap=0.25)
    fig = base_layout(fig, height=height)

    # La semana en curso está incompleta (no mezclarla visualmente con
    # semanas cerradas sin avisar): se conserva en el gráfico pero su
    # etiqueta la identifica como "Semana actual" en vez de un rango de
    # fechas, de forma consistente en todas las páginas que usan esta
    # función.
    hoy = pd.Timestamp.now().normalize()
    semana_actual_inicio = hoy - pd.Timedelta(days=hoy.weekday())
    semanas = sorted(semanal["semana_inicio"].unique())
    ticktext = []
    for s in semanas:
        ts = pd.Timestamp(s)
        rango = _fmt_semana_es(ts)
        ticktext.append(f"Semana actual<br>{rango}" if ts == semana_actual_inicio else rango)
    fig.update_xaxes(tickmode="array", tickvals=semanas, ticktext=ticktext)
    return fig


def fig_horas_por_dia(df: pd.DataFrame, height: int = 300) -> go.Figure:
    """Horas por fecha exacta (granularidad diaria, usada en Análisis)."""
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    diario = df.groupby("fecha", as_index=False)["horas"].sum().sort_values("fecha")
    fig = px.bar(diario, x="fecha", y="horas", labels={"fecha": "Fecha", "horas": "Horas"})
    fig.update_traces(marker_color=ACCENT, marker_line_width=0)
    return base_layout(fig, height=height, legend=False)


def fig_actividades_por_dia(df: pd.DataFrame, height: int = 300) -> go.Figure:
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    diario = df.groupby("fecha", as_index=False).size().rename(columns={"size": "actividades"}).sort_values("fecha")
    fig = px.bar(diario, x="fecha", y="actividades", labels={"fecha": "Fecha", "actividades": "Actividades"})
    fig.update_traces(marker_color="#eb6834", marker_line_width=0)
    return base_layout(fig, height=height, legend=False)


def fig_donut_proyecto(df: pd.DataFrame, height: int = 300) -> go.Figure:
    if df.empty or df["horas"].fillna(0).sum() == 0:
        return empty_figure("No hay horas registradas para los filtros seleccionados", height)
    cmap = color_map(df["proyecto"].unique().tolist(), COLOR_PROYECTO_BRAND)
    por_proyecto = df.groupby("proyecto", as_index=False)["horas"].sum()
    fig = px.pie(por_proyecto, names="proyecto", values="horas", hole=0.62,
                  color="proyecto", color_discrete_map=cmap)
    fig.update_traces(textinfo="percent", textfont_color="#ffffff",
                        marker=dict(line=dict(color=SURFACE, width=2)))
    return base_layout(fig, height=height)


def fig_donut_estado(df: pd.DataFrame, height: int = 300) -> go.Figure:
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    por_estado = df.groupby("estado", as_index=False).size().rename(columns={"size": "actividades"})
    cmap = {e: COLOR_ESTADO.get(e, INK_MUTED) for e in por_estado["estado"]}
    fig = px.pie(por_estado, names="estado", values="actividades", hole=0.62,
                  color="estado", color_discrete_map=cmap,
                  category_orders={"estado": data_mod.ESTADO_ORDEN})
    fig.update_traces(textinfo="percent", textfont_color="#ffffff",
                        marker=dict(line=dict(color=SURFACE, width=2)))
    return base_layout(fig, height=height)


def fig_barras_horas(df: pd.DataFrame, group_col: str, color: str | dict[str, str] = ACCENT,
                       height: int = 300, top_n: int | None = None) -> go.Figure:
    """Barra horizontal de horas agrupadas por group_col (tipo_actividad,
    categoria, proyecto, etc.), ordenada ascendente para que la barra más
    larga quede arriba. Si top_n se da, agrupa el resto en 'Otras'. `color`
    puede ser un solo hue (ranking de muchos ítems similares) o un dict
    valor->color (identidad, p.ej. por proyecto)."""
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    agg = df.groupby(group_col, as_index=False)["horas"].sum().sort_values("horas", ascending=False)
    if top_n and len(agg) > top_n:
        top = agg.iloc[:top_n]
        otras = pd.DataFrame([{group_col: "Otras", "horas": agg.iloc[top_n:]["horas"].sum()}])
        agg = pd.concat([top, otras])
    agg = agg.sort_values("horas", ascending=True)
    if isinstance(color, dict):
        fig = px.bar(agg, x="horas", y=group_col, orientation="h", color=group_col,
                      color_discrete_map=color, labels={"horas": "Horas", group_col: ""})
        fig.update_traces(marker_line_width=0)
        return base_layout(fig, height=height, legend=False)
    fig = px.bar(agg, x="horas", y=group_col, orientation="h",
                  labels={"horas": "Horas", group_col: ""})
    fig.update_traces(marker_color=color, marker_line_width=0)
    return base_layout(fig, height=height, legend=False)


def fig_barras_actividades(df: pd.DataFrame, group_col: str, color: str = ACCENT,
                             height: int = 300, top_n: int | None = None) -> go.Figure:
    """Igual que fig_barras_horas pero contando actividades en vez de horas."""
    if df.empty:
        return empty_figure("No hay actividades para los filtros seleccionados", height)
    agg = df.groupby(group_col, as_index=False).size().rename(columns={"size": "actividades"})
    agg = agg.sort_values("actividades", ascending=False)
    if top_n and len(agg) > top_n:
        top = agg.iloc[:top_n]
        otras = pd.DataFrame([{group_col: "Otras", "actividades": agg.iloc[top_n:]["actividades"].sum()}])
        agg = pd.concat([top, otras])
    agg = agg.sort_values("actividades", ascending=True)
    fig = px.bar(agg, x="actividades", y=group_col, orientation="h",
                  labels={"actividades": "Actividades", group_col: ""})
    fig.update_traces(marker_color=color, marker_line_width=0)
    return base_layout(fig, height=height, legend=False)


def fig_donut_hallazgo_estado(df: pd.DataFrame, height: int = 300) -> go.Figure:
    if df.empty:
        return empty_figure("No hay hallazgos para los filtros seleccionados", height)
    por_estado = df.groupby("Estado", as_index=False).size().rename(columns={"size": "hallazgos"})
    cmap = {e: HALLAZGO_ESTADO_COLOR.get(e, INK_MUTED) for e in por_estado["Estado"]}
    fig = px.pie(por_estado, names="Estado", values="hallazgos", hole=0.62,
                  color="Estado", color_discrete_map=cmap,
                  category_orders={"Estado": data_mod.HALLAZGOS_ESTADOS})
    fig.update_traces(textinfo="percent", textfont_color="#ffffff",
                        marker=dict(line=dict(color=SURFACE, width=2)))
    return base_layout(fig, height=height)


def fig_hallazgos_por_motor(df: pd.DataFrame, height: int = 320, top_n: int = 10) -> go.Figure:
    """Barra horizontal de cantidad de hallazgos por motor, mayor a menor."""
    if df.empty:
        return empty_figure("No hay hallazgos para los filtros seleccionados", height)
    agg = df.groupby("Motor", as_index=False).size().rename(columns={"size": "hallazgos"})
    agg = agg.sort_values("hallazgos", ascending=False)
    if len(agg) > top_n:
        top = agg.iloc[:top_n]
        otras = pd.DataFrame([{"Motor": "Otros", "hallazgos": agg.iloc[top_n:]["hallazgos"].sum()}])
        agg = pd.concat([top, otras])
    agg = agg.sort_values("hallazgos", ascending=True)
    fig = px.bar(agg, x="hallazgos", y="Motor", orientation="h",
                  labels={"hallazgos": "Hallazgos", "Motor": ""})
    fig.update_traces(marker_color=ACCENT, marker_line_width=0)
    return base_layout(fig, height=height, legend=False)


def fig_timeline(df: pd.DataFrame, height: int | None = None) -> go.Figure:
    tl = df.dropna(subset=["inicio_dt", "fin_dt"]).copy()
    if tl.empty:
        return empty_figure("No hay actividades con fecha/hora completas para graficar")
    cmap = color_map(tl["proyecto"].unique().tolist(), COLOR_PROYECTO_BRAND)
    tl = tl.sort_values("inicio_dt")
    tl["etiqueta"] = tl["actividad_id"] + " · " + tl["actividad"].str.slice(0, 55)
    fig = px.timeline(
        tl, x_start="inicio_dt", x_end="fin_dt", y="etiqueta", color="proyecto",
        color_discrete_map=cmap, category_orders={"proyecto": sorted(tl["proyecto"].unique())},
        hover_data={"estado": True, "categoria": True, "horas": ":.1f"},
    )
    fig.update_yaxes(autorange="reversed")
    return base_layout(fig, height=height or max(340, 24 * len(tl)))


def fig_horas_por_proyecto_comparativa(df: pd.DataFrame, height: int = 280) -> go.Figure:
    """Barra horizontal Sentinel Alerts vs New Opps vs Transversal — usada en
    Análisis para responder directamente '¿dónde se concentran mis horas?'."""
    cmap = color_map(df["proyecto"].unique().tolist(), COLOR_PROYECTO_BRAND) if not df.empty else {}
    return fig_barras_horas(df, "proyecto", color=cmap, height=height)
