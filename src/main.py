"""
Punto de entrada principal de Reversa.

Ejecutar:
    uv run python src/main.py
"""

from __future__ import annotations

from src.api import BOEDownloader


def main() -> None:
    """Ejecuta el pipeline completo de Reversa."""
    resumen = BOEDownloader().descargar_masivo()
    print(
        f"Descarga completada: {resumen.descargados} descargados, "
        f"{resumen.saltados} saltados, {resumen.fallidos} fallidos "
        f"(total: {resumen.total})"
    )


if __name__ == "__main__":
    main()
