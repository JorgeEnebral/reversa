"""
Punto de entrada principal de Reversa.

Ejecutar:
    uv run python src/main.py
"""

from __future__ import annotations

from src.api import BOEDownloader
from src.preprocess import Preprocesador


def main() -> None:
    """Ejecuta el pipeline completo de Reversa."""

    resumen_downloader = BOEDownloader().descargar_masivo()
    print(
        f"Descarga completada: {resumen_downloader.descargados} descargados, "
        f"{resumen_downloader.saltados} saltados, "
        f"{resumen_downloader.fallidos} fallidos "
        f"(total: {resumen_downloader.total})"
    )

    resumen_preprocesador = Preprocesador().preprocesar_todo()
    print(
        f"Preprocesado completado: "
        f"{resumen_preprocesador.nodos_upsert} nodos insertados, "
        f"{resumen_preprocesador.aristas_upsert} aristas insertadas,"
        f"{resumen_preprocesador.errores} fallidos, "
        f"(total: {resumen_preprocesador.procesadas})"
    )


if __name__ == "__main__":
    main()
