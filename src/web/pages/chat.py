"""
Página /chat — interfaz conversacional con streaming.

Layout: header de navegación + área de mensajes + input autogrow + botón enviar.
La respuesta del LLM se renderiza token a token vía AsyncAnthropic.
"""

from __future__ import annotations

import asyncio

import structlog
from nicegui import ui

from src.llm import Llm

log = structlog.get_logger()

_DARK_BG = "background:#0d0d1a;color:#e0e0e0;"
_MSG_USER = (
    "background:#1e3a5f;color:#e0e0e0;border-radius:12px;"
    "padding:10px 14px;max-width:80%;align-self:flex-end;"
)
_MSG_BOT = (
    "background:#1e1e3f;color:#e0e0e0;border-radius:12px;"
    "padding:10px 14px;max-width:80%;align-self:flex-start;"
)


def build_chat_header() -> None:
    """Renderiza el header de navegación compartido."""
    with ui.header().style("background:#0d0d1a;border-bottom:1px solid #333;"):
        with ui.row().classes("w-full items-center justify-between px-4"):
            ui.link("🕸 Reversa", "/").style(
                "color:#7eb8f7;font-size:1.3em;font-weight:bold;text-decoration:none;"
            )
            ui.link("Grafo", "/graph").style("color:#aaa;text-decoration:none;")


def register_chat_page() -> None:
    """Registra las rutas / y /chat en NiceGUI."""

    @ui.page("/")
    @ui.page("/chat")
    async def chat_page() -> None:
        """Página principal de chat con streaming del LLM."""
        llm = Llm()

        ui.add_head_html(
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
        )

        build_chat_header()

        with ui.column().style(
            f"width:100%;max-width:800px;margin:0 auto;height:calc(100vh - 60px);"
            f"display:flex;flex-direction:column;{_DARK_BG}"
        ):
            # Área de mensajes
            with ui.scroll_area().style(
                "flex:1;overflow-y:auto;padding:16px;"
            ) as scroll:
                messages_col = ui.column().classes("w-full gap-3")

            # Input + botón
            with ui.row().style(
                "padding:12px;gap:8px;background:#0d0d1a;"
                "border-top:1px solid #333;"
            ):
                query_input = (
                    ui.textarea(placeholder="Escribe tu pregunta sobre el BOE…")
                    .props("autogrow rows=1 outlined")
                    .style(
                        "flex:1;background:#1e1e3f;color:#e0e0e0;"
                        "border-radius:8px;"
                    )
                )
                send_btn = (
                    ui.button("→")
                    .props("flat")
                    .style("color:#7eb8f7;font-size:1.4em;align-self:flex-end;")
                )

        async def send() -> None:
            """Envía la pregunta al LLM y hace streaming de la respuesta."""
            query = query_input.value.strip()
            if not query:
                return

            query_input.value = ""
            send_btn.disable()

            # Mensaje del usuario
            with messages_col:
                ui.label(query).style(_MSG_USER)

            # Placeholder del bot
            with messages_col:
                bot_label = ui.markdown("").style(_MSG_BOT)

            scroll.scroll_to(percent=1.0)

            # Streaming
            buffer = ""
            try:
                async for token in llm.responder(query):
                    buffer += token
                    bot_label.set_content(buffer)
                    scroll.scroll_to(percent=1.0)
                    await asyncio.sleep(0)
            except Exception as exc:
                log.error("stream_error", error=str(exc))
                bot_label.set_content(
                    "⚠ Error al conectar con el LLM. Comprueba ANTHROPIC_API_KEY."
                )
            finally:
                send_btn.enable()

        send_btn.on("click", send)
        query_input.on(
            "keydown.enter",
            lambda e: send() if not e.args.get("shiftKey") else None,
        )
