#!/usr/bin/env bash
# PreToolUse hook: bloquea cualquier acceso a ficheros .env
#
# Recibe por stdin un JSON {tool_name, tool_input, ...}. Si la herramienta
# apunta a un .env (por file_path o por contenido del comando), sale con
# código 2 y un motivo en stderr, lo que aborta la llamada antes de ejecutarla.

set -uo pipefail

# Verificar dependencia
if ! command -v jq &>/dev/null; then
    echo "Hook error: jq no encontrado." >&2
    exit 1
fi

payload="$(cat)"
tool_name="$(printf '%s' "$payload" | jq -r '.tool_name // ""')"

# Patrón: .env, .env.local, .env.production, etc. Permite .env.example (solo lectura).
is_env_path() {
    local p="$1"
    [[ "$p" =~ (^|/)\.env($|\.[^/]*$) ]] && [[ ! "$p" =~ \.env\.example$ ]]
}

block() {
    echo "Bloqueado por hook: acceso a .env prohibido ($1)." >&2
    exit 2
}

case "$tool_name" in
    Read|Edit|Write|MultiEdit|NotebookEdit)
        path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // ""')"
        if is_env_path "$path"; then
            block "$path"
        fi
        ;;
    Grep)
        path="$(printf '%s' "$payload" | jq -r '.tool_input.path // ""')"
        if is_env_path "$path"; then
            block "$path"
        fi
        ;;
    Bash)
        cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // ""')"
        # Detecta tokens \.env en el comando, ignorando .env.example
        if printf '%s' "$cmd" \
                | grep -Eq '(^|[[:space:]/"'\''=])\.env([[:space:]"'\''&|;>)]|$)|/\.env([[:space:]"'\''&|;>)]|$)'; then
            if ! printf '%s' "$cmd" | grep -q '\.env\.example'; then
                block "comando bash referencia .env"
            fi
        fi
        ;;
esac

exit 0