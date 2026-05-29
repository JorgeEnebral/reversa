# Bucle de chat base con soporte de tool use.
# Gestiona el historial de mensajes y el ciclo de razonamiento de Claude:
#   1. Envía el mensaje a Claude con las tools disponibles.
#   2. Si Claude responde con tool_use, ejecuta las tools y vuelve a llamar a Claude.
#   3. Repite hasta que Claude responde sin invocar ninguna tool (stop_reason != "tool_use").
# Las subclases pueden sobreescribir _process_query para transformar el input del usuario
# antes de añadirlo al historial (por ejemplo, CliChat inyecta contexto de documentos).

from core.claude import Claude
from mcp_client import MCPClient
from core.tools import ToolManager
from anthropic.types import MessageParam


class Chat:
    def __init__(self, claude_service: Claude, clients: dict[str, MCPClient]):
        self.claude_service: Claude = claude_service
        self.clients: dict[str, MCPClient] = clients
        # Historial acumulativo de la conversación; crece con cada turno usuario/asistente
        self.messages: list[MessageParam] = []

    async def _process_query(self, query: str):
        # Comportamiento base: añade el texto del usuario directamente al historial.
        # CliChat sobreescribe este método para enriquecer el query con contexto adicional.
        self.messages.append({"role": "user", "content": query})

    async def run(self, query: str) -> str:
        final_text_response = ""

        # Prepara el mensaje (puede enriquecerse en subclases) y lo añade al historial
        await self._process_query(query)

        # Bucle de tool use: Claude puede invocar varias tools en secuencia
        # antes de dar su respuesta final de texto
        while True:
            response = self.claude_service.chat(
                messages=self.messages,
                tools=await ToolManager.get_all_tools(self.clients),
            )

            # Añade la respuesta de Claude al historial para mantener el contexto
            self.claude_service.add_assistant_message(self.messages, response)

            if response.stop_reason == "tool_use":
                # Claude quiere usar una o más tools: muestra el texto intermedio si lo hay
                print(self.claude_service.text_from_message(response))

                # Ejecuta todas las tools solicitadas y recoge los resultados
                tool_result_parts = await ToolManager.execute_tool_requests(
                    self.clients, response
                )

                # Devuelve los resultados a Claude como turno de usuario para que continúe
                self.claude_service.add_user_message(
                    self.messages, tool_result_parts
                )
            else:
                # Claude ha terminado: respuesta de texto final sin más tool calls
                final_text_response = self.claude_service.text_from_message(
                    response
                )
                break

        return final_text_response
