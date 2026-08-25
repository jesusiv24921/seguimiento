"""Asistente IA — chat con acceso a los datos reales de Seguimiento (vía
ai_assistant.py, function calling sobre la Responses API de OpenAI).

El historial se guarda en disco (un JSON por conversación) por ai_assistant.py
— esta página solo orquesta la interfaz: elegir/crear conversación, mandar
mensajes, mostrarlos. Nunca llama a OpenAI directamente ni ve la API key.
"""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

import ai_assistant as ai
from components import chart_card, page_header

dash.register_page(__name__, path="/asistente", name="Asistente", title="Asistente")


_FUENTE_LABELS = {
    "local": "🟢 Datos de Seguimiento · Sin uso de IA",
    "conocimiento": "📚 Centro de Conocimiento · Sin uso de IA",
    "ia": "🤖 Generado con IA",
    "ia_cache": "🤖 Generado con IA (caché)",
    "sistema": "⚠️ Aviso del sistema",
}


def _burbuja(mensaje: dict) -> html.Div:
    es_usuario = mensaje.get("rol") == "user"
    hijos = [dcc.Markdown(mensaje.get("contenido", ""), className="ast-burbuja-texto")]
    fuente = mensaje.get("fuente")
    if not es_usuario and fuente in _FUENTE_LABELS:
        hijos.append(html.Div(_FUENTE_LABELS[fuente], className="ast-burbuja-fuente"))
    return html.Div(
        className=f"ast-burbuja {'ast-burbuja-usuario' if es_usuario else 'ast-burbuja-asistente'}",
        children=hijos,
    )


def _sin_configurar() -> html.Div:
    return html.Div(className="empty-state", children=[
        html.I(className="bi bi-robot"),
        html.Div("El asistente no está activado todavía."),
        html.Div("Falta configurar la variable de entorno OPENAI_API_KEY.", className="section-caption"),
    ])


layout = html.Div(className="page", children=[
    page_header("Asistente", "Pregúntale sobre tus proyectos, pendientes, bloqueos y conocimiento guardado — "
                 "consulta tus datos reales, nunca inventa cifras."),

    dcc.Store(id="store-conversacion-actual"),

    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-chat-dots"), "Conversación"], className="section-title"),
            dcc.Dropdown(id="ast-selector-conversacion", placeholder="Conversaciones anteriores...",
                          style={"minWidth": "260px"}, className="flex-grow-1"),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nueva conversación"],
                        id="ast-btn-nueva-conversacion", className="btn-refresh", n_clicks=0),
        ], style={"justifyContent": "space-between", "alignItems": "center", "flexWrap": "wrap"}),
    ]) if ai.is_configured() else None,

    chart_card([
        html.Div([html.I(className="bi bi-graph-up"), "Consumo de IA"], className="section-title"),
        html.Div("Estimado por Seguimiento a partir del uso registrado — no es el saldo real de tu "
                  "cuenta de OpenAI, que solo puedes ver en platform.openai.com.", className="section-caption"),
        html.Div(id="ast-consumo-resumen"),
    ]) if ai.is_configured() else None,

    chart_card([
        _sin_configurar() if not ai.is_configured() else html.Div([
            html.Div(id="ast-mensajes", className="ast-mensajes"),
            html.Div(id="ast-error"),
            dcc.Loading(type="circle", children=html.Div(className="ast-input-row", children=[
                dbc.Textarea(id="ast-input", placeholder="Escribe tu pregunta...",
                              style={"height": "60px"}, className="flex-grow-1"),
                dbc.Button(html.I(className="bi bi-send-fill"), id="ast-btn-enviar",
                            className="btn-refresh", n_clicks=0),
            ])),
            html.Div(id="ast-mermaid-trigger", style={"display": "none"}),
        ]),
    ]),
])


if ai.is_configured():

    @dash.callback(
        Output("ast-selector-conversacion", "options"),
        Input("url", "pathname"),
        Input("store-conversacion-actual", "data"),
        prevent_initial_call=True,
    )
    def actualizar_lista_conversaciones(pathname, _conv_actual):
        if pathname != "/asistente":
            return dash.no_update
        conversaciones = ai.listar_conversaciones()
        return [{"label": c["titulo"], "value": c["conversacion_id"]} for c in conversaciones]

    @dash.callback(
        Output("store-conversacion-actual", "data"),
        Output("ast-mensajes", "children"),
        Output("ast-input", "value"),
        Input("url", "pathname"),
        Input("ast-btn-nueva-conversacion", "n_clicks"),
        Input("ast-selector-conversacion", "value"),
        State("store-prompt-pendiente", "data"),
        prevent_initial_call=True,
    )
    def cambiar_conversacion(pathname, n_nueva, conversacion_elegida, prompt_pendiente):
        triggered = dash.ctx.triggered_id

        if triggered == "url":
            if pathname != "/asistente":
                return dash.no_update, dash.no_update, dash.no_update
            cid = ai.nueva_conversacion_id()
            return cid, [], (prompt_pendiente or "")

        if triggered == "ast-btn-nueva-conversacion":
            if not n_nueva:
                return dash.no_update, dash.no_update, dash.no_update
            return ai.nueva_conversacion_id(), [], ""

        if triggered == "ast-selector-conversacion":
            if not conversacion_elegida:
                return dash.no_update, dash.no_update, dash.no_update
            historial = ai.obtener_conversacion(conversacion_elegida)
            burbujas = [_burbuja(m) for m in historial.get("mensajes", [])]
            return conversacion_elegida, burbujas, ""

        return dash.no_update, dash.no_update, dash.no_update

    @dash.callback(
        Output("store-prompt-pendiente", "data", allow_duplicate=True),
        Input("store-conversacion-actual", "data"),
        prevent_initial_call=True,
    )
    def limpiar_prompt_pendiente(_conv_id):
        return None

    @dash.callback(
        Output("ast-mensajes", "children", allow_duplicate=True),
        Output("ast-input", "value", allow_duplicate=True),
        Output("ast-error", "children"),
        Input("ast-btn-enviar", "n_clicks"),
        State("ast-input", "value"),
        State("store-conversacion-actual", "data"),
        State("ast-mensajes", "children"),
        prevent_initial_call=True,
    )
    def enviar_mensaje(n_clicks, texto, conversacion_id, burbujas_actuales):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update
        if not texto or not texto.strip():
            return dash.no_update, dash.no_update, html.Div(
                "Escribe un mensaje antes de enviar.", className="section-caption", style={"color": "#a52323"})
        if not conversacion_id:
            conversacion_id = ai.nueva_conversacion_id()

        # El router de ai_assistant.py intenta responder sin OpenAI primero
        # (ok siempre es True para esas rutas); ok=False solo ocurre por un
        # bloqueo de presupuesto/límite diario o un error real de conexión.
        # En ambos casos igual se muestra como burbuja (con su etiqueta de
        # fuente) para que quede claro qué pasó, y el texto se deja en el
        # cuadro de entrada para poder reintentar.
        ok, respuesta, fuente = ai.enviar_mensaje(conversacion_id, texto.strip())
        burbujas_actuales = burbujas_actuales or []
        nuevas = burbujas_actuales + [
            _burbuja({"rol": "user", "contenido": texto.strip()}),
            _burbuja({"rol": "assistant", "contenido": respuesta, "fuente": fuente}),
        ]
        return nuevas, ("" if ok else texto), None

    @dash.callback(
        Output("ast-consumo-resumen", "children"),
        Input("url", "pathname"),
        Input("ast-mensajes", "children"),
    )
    def actualizar_consumo(_pathname, _mensajes):
        r = ai.resumen_consumo_mes()
        pct = min(r["porcentaje_usado"], 100)
        if pct < 80:
            color = "var(--good)"
        elif pct < 100:
            color = "var(--warning)"
        else:
            color = "var(--critical)"
        return html.Div([
            html.Div(className="ast-consumo-stats", children=[
                html.Div([html.Div(str(r["consultas_ia"]), className="kpi-value"),
                           html.Div("Consultas con IA", className="kpi-label")]),
                html.Div([html.Div(str(r["consultas_locales"]), className="kpi-value"),
                           html.Div("Resueltas sin IA", className="kpi-label")]),
                html.Div([html.Div(f"{r['tokens_totales']:,}", className="kpi-value"),
                           html.Div("Tokens usados", className="kpi-label")]),
                html.Div([html.Div(f"${r['costo_estimado_usd']:.2f}", className="kpi-value"),
                           html.Div("Costo estimado", className="kpi-label")]),
            ]),
            html.Div(className="ast-budget-bar-track", children=[
                html.Div(className="ast-budget-bar-fill", style={"width": f"{pct}%", "backgroundColor": color}),
            ]),
            html.Div(f"${r['costo_estimado_usd']:.2f} de ${r['presupuesto_usd']:.2f} "
                      f"presupuestados este mes ({r['porcentaje_usado']:.1f}%)", className="section-caption"),
        ])

    # Los mapas conceptuales que pide el asistente vienen como bloque
    # ```mermaid dentro del Markdown de la respuesta; dcc.Markdown los
    # renderiza como <code class="language-mermaid">, no como mermaid.js
    # espera (<div class="mermaid">) — este callback clientside los convierte
    # y llama a mermaid.run() cada vez que aparecen mensajes nuevos.
    dash.clientside_callback(
        """
        function(children) {
            setTimeout(function() {
                if (window.mermaid) {
                    document.querySelectorAll('code.language-mermaid').forEach(function(el) {
                        if (el.dataset.mermaidDone) { return; }
                        el.dataset.mermaidDone = "1";
                        var pre = el.closest('pre');
                        var div = document.createElement('div');
                        div.className = 'mermaid';
                        div.textContent = el.textContent;
                        if (pre && pre.parentNode) { pre.parentNode.replaceChild(div, pre); }
                    });
                    window.mermaid.run();
                }
            }, 60);
            return '';
        }
        """,
        Output("ast-mermaid-trigger", "children"),
        Input("ast-mensajes", "children"),
    )
