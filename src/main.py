"""
Punto de entrada principal de Reversa.

Arranca la interfaz web NiceGUI (que incluye su propio servidor uvicorn).
Para el pipeline de descarga + preprocesado usar api.py / preprocess.py
directamente o crear un comando CLI separado.

Ejecutar:
    uv run python -m src.main
"""

from src.config import settings
from src.web.app import create_app

from src.api import BOEDownloader
from src.preprocess import Preprocesador



def main() -> None:
    """Registra las páginas y arranca NiceGUI."""
    # create_app()
    # ui.run(
    #     host=settings.web.host,
    #     port=settings.web.port,
    #     title=settings.web.title,
    #     reload=False,
    #     dark=True,
    # )
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
