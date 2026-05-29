"""
CLI de Reversa.

Uso:
    python -m reversa.cli api masivo
    python -m reversa.cli api reintentar
    python -m reversa.cli api selectivo --ids BOE-A-2015-10565,BOE-A-2015-10566
    python -m reversa.cli api selectivo --from-file ids_extras.txt
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Reversa — BOE knowledge graph CLI")
api_app = typer.Typer(help="Comandos de descarga de la API del BOE")
app.add_typer(api_app, name="api")


@api_app.command("masivo")
def cmd_masivo(force: bool = typer.Option(False, help="Fuerza re-descarga del listado")) -> None:
    """Pipeline completo de descarga. Idempotente."""
    from api.downloader import BOEDownloader

    resumen = BOEDownloader().descargar_masivo(force=force)
    typer.echo(
        f"Completado: {resumen.descargados} descargados, "
        f"{resumen.saltados} saltados, {resumen.fallidos} fallidos "
        f"(total: {resumen.total})"
    )


@api_app.command("reintentar")
def cmd_reintentar() -> None:
    """Reintenta los IDs con error en data_api/errors/."""
    from api.downloader import BOEDownloader

    resumen = BOEDownloader().reintentar()
    typer.echo(f"Recuperados: {resumen.recuperados} / {resumen.total_intentados}")


@api_app.command("selectivo")
def cmd_selectivo(
    ids: str = typer.Option("", help="IDs separados por coma"),
    from_file: Path = typer.Option(None, help="Fichero con un ID por línea"),
) -> None:
    """Descarga una lista concreta de IDs."""
    from api.downloader import BOEDownloader

    id_list: list[str] = []
    if from_file:
        id_list = from_file.read_text().splitlines()
    elif ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
    else:
        typer.echo("Debes proporcionar --ids o --from-file", err=True)
        raise typer.Exit(1)

    resumen = BOEDownloader().descargar_selectivo(id_list)
    typer.echo(
        f"Completado: {resumen.descargados} descargados, "
        f"{resumen.saltados} saltados, {resumen.fallidos} fallidos"
    )


if __name__ == "__main__":
    app()
