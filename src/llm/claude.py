# Wrapper sobre el cliente de la API de Anthropic.
# Centraliza toda la lógica de llamadas a Claude: construcción de mensajes,
# extracción de texto, y parámetros opcionales como tools, thinking y stop sequences.

from anthropic import Anthropic
from anthropic.types import Message


class Claude:
    def __init__(self, model: str):
        # Anthropic() lee ANTHROPIC_API_KEY del entorno automáticamente
        self.client = Anthropic()
        self.model = model

    def add_user_message(self, messages: list, message):
        # Añade un turno de usuario al historial de mensajes.
        # Acepta tanto un objeto Message de Anthropic como texto plano o lista de bloques
        # (p.ej. lista de ToolResultBlockParam cuando se devuelven resultados de tools).
        user_message = {
            "role": "user",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(user_message)

    def add_assistant_message(self, messages: list, message):
        # Añade un turno de asistente al historial.
        # Igual que add_user_message pero con role="assistant".
        assistant_message = {
            "role": "assistant",
            "content": message.content
            if isinstance(message, Message)
            else message,
        }
        messages.append(assistant_message)

    def text_from_message(self, message: Message) -> str:
        # Extrae y concatena solo los bloques de tipo "text" de una respuesta de Claude.
        # Ignora bloques tool_use, thinking, etc.
        return "\n".join(
            [block.text for block in message.content if block.type == "text"]
        )

    def chat(
        self,
        messages,
        system=None,          # System prompt opcional
        temperature=1.0,       # Controla la aleatoriedad de la respuesta
        stop_sequences=[],     # Secuencias de texto que detienen la generación
        tools=None,            # Lista de tools en formato Anthropic que Claude puede invocar
        thinking=False,        # Activa el modo "extended thinking" (razonamiento visible)
        thinking_budget=1024,  # Tokens máximos reservados para el razonamiento interno
    ) -> Message:
        params = {
            "model": self.model,
            "max_tokens": 8000,
            "messages": messages,
            "temperature": temperature,
            "stop_sequences": stop_sequences,
        }

        if thinking:
            # Extended thinking: Claude muestra su razonamiento antes de responder
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        if tools:
            params["tools"] = tools  # Claude usará stop_reason="tool_use" cuando quiera invocar una tool

        if system:
            params["system"] = system

        message = self.client.messages.create(**params)
        return message
