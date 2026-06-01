"""
Página ``/`` y ``/chat`` — interfaz conversacional con streaming del LLM.

Flujo de la UI
--------------
La página arranca en modo «hero»: logo + input centrados verticalmente.
Al enviar la primera pregunta se hace una transición única (``_activate_chat``)
que ancla el input en la parte inferior y muestra el historial de conversación
en un scroll area. Las respuestas del LLM se renderizan token a token
(streaming) actualizando un único widget Markdown para minimizar reflows.

Las burbujas de chat se posicionan con ``justify-end`` / ``justify-start``
dentro de rows de ancho completo para que el alineado derecha/izquierda
funcione sin conocer el ancho exacto de cada burbuja.
"""

from __future__ import annotations

import asyncio

import structlog
from nicegui import ui

from src.llm import Llm

log = structlog.get_logger()

# Estilos inline de burbujas y barra de input. Se definen como constantes de
# módulo para no mezclar CSS con la lógica de la función de página.
_MSG_USER = (
    "background:var(--brand);color:#fff;border-radius:16px 16px 4px 16px;"
    "padding:10px 15px;max-width:80%;font-size:0.95em;line-height:1.5;"
)
_MSG_BOT = (
    "background:var(--bot-bubble);color:var(--text);border-radius:16px 16px 16px 4px;"
    "padding:2px 16px;max-width:88%;font-size:0.95em;line-height:1.55;"
)
_INPUT_BAR = (
    "width:100%;display:flex;align-items:flex-end;gap:6px;"
    "background:var(--surface);border:1px solid var(--border);border-radius:18px;"
    "padding:6px 6px 6px 16px;box-shadow:0 2px 10px rgba(16,24,40,0.06);"
)


def build_chat_header() -> None:
    """Renderiza el header de navegación compartido entre chat y grafo.

    Se llama desde ``register_chat_page`` y también desde ``graph.py`` para
    que ambas páginas compartan el mismo header sin duplicar código.
    """
    with ui.header().style(
        "background:var(--bg);border-bottom:1px solid var(--border);"
        "box-shadow:none;min-height:60px;"
    ):
        with ui.row().classes("w-full items-center justify-between").style("padding:0 24px;"):
            with ui.link(target="/").style("display:flex;align-items:center;gap:8px;"):
                ui.image("/resources/logo.png").style("width:22px;height:auto;")
                ui.label("Reversa").style("color:var(--brand);font-size:1.2em;font-weight:700;")
            with ui.row().style("gap:24px;align-items:center;"):
                ui.link("Chat", "/chat").style("color:var(--text-muted);font-weight:500;")
                ui.link("Grafo", "/graph").style("color:var(--text-muted);font-weight:500;")


def register_chat_page(global_styles: str = "") -> None:
    """Registra las rutas ``/`` y ``/chat`` en NiceGUI.

    Ambas rutas mapean a la misma función de página. La ruta ``/`` sirve como
    landing page; ``/chat`` como enlace directo desde el header del grafo.

    Args:
        global_styles: HTML de estilos globales inyectado en el ``<head>``.
    """

    @ui.page("/")
    @ui.page("/chat")
    async def chat_page() -> None:
        """Página principal de chat con streaming token a token."""
        # Una instancia de Llm por sesión de usuario (cada visita a la página
        # crea su propio historial de conversación).
        llm = Llm()

        ui.add_head_html('<meta name="viewport" content="width=device-width,initial-scale=1">')
        if global_styles:
            ui.add_head_html(global_styles)

        build_chat_header()

        # Flag que controla la transición hero → conversación (ocurre una sola vez).
        started = False

        # Contenedor raíz en modo hero: centra verticalmente el logo y el input.
        # Al activar la conversación pasa a justify-content:flex-start.
        root = ui.column().style(
            "width:100%;max-width:760px;margin:0 auto;height:calc(100vh - 60px);"
            "display:flex;flex-direction:column;justify-content:center;"
            "gap:18px;padding:16px;"
        )
        with root:
            hero = ui.column().style("width:100%;align-items:center;gap:10px;")
            with hero:
                ui.image("/resources/logo_con_nombre.png").style("width:220px;height:auto;")
                ui.label("Tu copiloto jurídico sobre el BOE").style(
                    "color:var(--text-muted);font-size:1.05em;font-weight:500;"
                )

            # scroll_area envuelve el historial para que crezca hasta llenar el
            # espacio disponible y luego haga scroll, sin afectar al input.
            convo = ui.scroll_area().style("flex:1;width:100%;")
            with convo:
                messages_col = ui.column().style("width:100%;gap:16px;padding:8px 4px 16px;")
            convo.set_visibility(False)

            with ui.element("div").style(_INPUT_BAR):
                query_input = (
                    ui.textarea(placeholder="Pregunta sobre el BOE…")
                    .props("autogrow rows=1 borderless")
                    .style("flex:1;color:var(--text);font-size:1em;")
                )
                send_btn = (
                    ui.button(icon="arrow_upward")
                    .props("round dense unelevated")
                    .style("background:var(--brand);color:#fff;")
                )

        def _activate_chat() -> None:
            """Transición única: oculta el hero y muestra la conversación."""
            nonlocal started
            if started:
                return
            started = True
            hero.set_visibility(False)
            convo.set_visibility(True)
            root.style("justify-content:flex-start;")

        async def send() -> None:
            """Envía la pregunta al LLM y hace streaming de la respuesta.

            El botón se deshabilita durante el streaming para evitar envíos
            simultáneos. ``asyncio.sleep(0)`` cede el control al event loop
            de NiceGUI para que cada token actualice la UI en tiempo real.
            """
            query = query_input.value.strip()
            if not query:
                return

            _activate_chat()
            query_input.value = ""
            send_btn.disable()

            with messages_col:
                with ui.row().classes("w-full justify-end"):
                    ui.label(query).style(_MSG_USER)
                with ui.row().classes("w-full justify-start"):
                    bot_label = ui.markdown("").style(_MSG_BOT)
            convo.scroll_to(percent=1.0)

            buffer = ""
            try:
                async for token in llm.responder(query):
                    buffer += token
                    bot_label.set_content(buffer)
                    convo.scroll_to(percent=1.0)
                    await asyncio.sleep(0)
            except Exception as exc:  # noqa: BLE001
                log.error("stream_error", error=str(exc))
                bot_label.set_content(
                    "⚠ Error al conectar con el LLM. Comprueba ANTHROPIC_API_KEY."
                )
            finally:
                send_btn.enable()

        send_btn.on("click", send)
        # Enter envía; Shift+Enter inserta salto de línea (comportamiento estándar de chat).
        query_input.on(
            "keydown.enter",
            lambda e: send() if not e.args.get("shiftKey") else None,
        )
