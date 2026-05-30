"""
Descarga masiva de legislación consolidada del BOE.

Tres modos de uso:
  - descargar_masivo()       : pipeline completo, idempotente
  - reintentar()             : reintenta los IDs en ontology/kinetic-layer/api_boe/errors/
  - descargar_selectivo(ids) : descarga una lista concreta de IDs
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import httpx
import structlog
from lxml import etree
from tqdm import tqdm

from src.config import APIConfig, settings

log = structlog.get_logger()


@dataclass
class ResumenDescarga:
    """Resultado de una operación de descarga."""

    total: int = 0
    descargados: int = 0
    fallidos: int = 0
    saltados: int = 0


@dataclass
class ResumenReintento:
    """Resultado de reintentar los errores pendientes."""

    recuperados: int = 0
    total_intentados: int = 0


class BOEDownloader:
    """Cliente de descarga de la API de legislación consolidada del BOE.

    Args:
        config: Configuración de rutas y endpoint. Por defecto usa API_CONFIG.

    Example:
        >>> downloader = BOEDownloader()
        >>> resumen = downloader.descargar_masivo()
        >>> print(resumen.descargados, "/", resumen.total)
    """

    _LISTADO_ENDPOINT = "/legislacion-consolidada"
    _NORMA_ENDPOINT = "/legislacion-consolidada/id/{id}"

    def __init__(self, config: APIConfig = settings.api) -> None:
        self._cfg = config
        self._client = httpx.Client(timeout=config.timeout)

    # ------------------------------------------------------------------ #
    # Métodos públicos                                                     #
    # ------------------------------------------------------------------ #

    def descargar_masivo(self, force: bool = False) -> ResumenDescarga:
        """Pipeline completo de descarga. Idempotente.
        Descarga en ontology/kinetic-layer/api_boe/raw/

        Si ids.txt ya existe, no repide el listado (a menos que force=True).
        Si un XML ya existe en raw/, lo salta.
        Si un ID está en errors/, lo reintenta.

        Args:
            force: Si True, fuerza la re-descarga del listado de IDs.

        Returns:
            ResumenDescarga con totales de la operación.
        """
        self._cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        self._cfg.errors_dir.mkdir(parents=True, exist_ok=True)

        if not self._cfg.ids_file.exists() or force:
            log.info("\nObteniendo ids...")
            ids = self._obtener_ids_ordenados()
            self._persistir_ids(ids, self._cfg.ids_file)
        else:
            ids = self._cfg.ids_file.read_text().splitlines()
            log.info("\nListado existente", total=len(ids))

        resumen = ResumenDescarga(total=len(ids))
        log.info("\nProcesando ids...")
        with tqdm(ids, unit="norma", dynamic_ncols=True) as bar:
            for norm_id in bar:
                bar.set_postfix_str(norm_id, refresh=False)
                self._procesar_id(norm_id, resumen)

        log.info(
            "\nDescarga masiva completada",
            total=resumen.total,
            descargados=resumen.descargados,
            fallidos=resumen.fallidos,
            saltados=resumen.saltados,
        )
        self.reintentar()
        return resumen

    def reintentar(self) -> ResumenReintento:
        """Reintenta todos los IDs en ontology/kinetic-layer/api_boe/errors/.

        Para cada error: si tiene éxito, borra el fichero de error y guarda
        el XML. Si falla, incrementa el campo `attempts` en el JSON.

        Returns:
            ResumenReintento con recuperados y total_intentados.
        """
        self._cfg.errors_dir.mkdir(parents=True, exist_ok=True)

        error_files = list(self._cfg.errors_dir.glob("*.json"))
        resumen = ResumenReintento(total_intentados=len(error_files))

        for error_file in error_files:
            error_data = json.loads(error_file.read_text())
            norm_id: str = error_data["id"]
            try:
                xml_bytes = self._descargar_xml(norm_id)
                destino = self._ruta_xml_por_id(norm_id)
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(xml_bytes)
                error_file.unlink()
                resumen.recuperados += 1
                log.info("\nReintento exitoso", id=norm_id)
            except Exception as exc:  # noqa: BLE001
                error_data["attempts"] = error_data.get("attempts", 1) + 1
                error_data["error"] = str(exc)
                error_file.write_text(
                    json.dumps(error_data, ensure_ascii=False)
                )
                log.warning("\nReintento fallido", id=norm_id, error=str(exc))

        log.info(
            "\nReintento completado",
            recuperados=resumen.recuperados,
            total=resumen.total_intentados,
        )
        return resumen

    def descargar_selectivo(self, ids: list[str]) -> ResumenDescarga:
        """Descarga una lista concreta de IDs sin repedir el listado completo.

        Args:
            ids: Lista de identificadores BOE (e.g. ['BOE-A-2015-10565']).

        Returns:
            ResumenDescarga con totales de la operación.
        """
        self._cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        self._cfg.errors_dir.mkdir(parents=True, exist_ok=True)

        resumen = ResumenDescarga(total=len(ids))
        for norm_id in ids:
            self._procesar_id(norm_id, resumen)

        log.info(
            "\nDescarga selectiva completada",
            total=resumen.total,
            descargados=resumen.descargados,
            fallidos=resumen.fallidos,
            saltados=resumen.saltados,
        )
        return resumen

    # ------------------------------------------------------------------ #
    # Internos                                                             #
    # ------------------------------------------------------------------ #

    def _obtener_ids_ordenados(self) -> list[str]:
        """Obtiene todos los IDs del listado de legislación ordenados por fecha ASC."""
        ids_con_fecha: list[dict[str, Any]] = []
        offset = 0
        limit = 10_000

        while True:
            response = self._client.get(
                f"{self._cfg.base_url}{self._LISTADO_ENDPOINT}",
                params={"offset": offset, "limit": limit},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            body = response.json()

            # La API devuelve "" cuando offset supera el total
            data = body.get("data", [])
            if not data or not isinstance(data, list):
                break

            ids_con_fecha.extend(
                {
                    "id": item["identificador"],
                    "fecha": item.get("fecha_publicacion", ""),
                }
                for item in data
                if "identificador" in item
            )
            log.info("Listado pagina", offset=offset, obtenidos=len(data))

            if len(data) < limit:
                break
            offset += limit

        ids_con_fecha.sort(key=lambda x: x["fecha"])
        return [item["id"] for item in ids_con_fecha]

    def _persistir_ids(self, ids: list[str], destino: Path) -> None:
        """Guarda los IDs en un fichero txt, uno por línea."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("\n".join(ids))
        log.info("\nIds persistidos", total=len(ids), path=str(destino))

    def _procesar_id(self, norm_id: str, resumen: ResumenDescarga) -> None:
        """Descarga un único ID actualizando el resumen en lugar."""
        # Si ya existe en raw/, saltar
        destino = self._ruta_xml_por_id(norm_id)
        if destino.exists():
            resumen.saltados += 1
            return

        try:
            xml_bytes = self._descargar_xml(norm_id)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(xml_bytes)
            resumen.descargados += 1
        except Exception as exc:  # noqa: BLE001
            self._persistir_error(norm_id, exc)
            resumen.fallidos += 1

    def _descargar_xml(self, norm_id: str) -> bytes:
        """Descarga el XML completo de una norma y valida que sea XML bien formado.

        Raises:
            httpx.HTTPStatusError: Si el servidor devuelve un código de error.
            etree.XMLSyntaxError: Si la respuesta no es XML válido.
        """
        time.sleep(self._cfg.wait)
        url = f"{self._cfg.base_url}{self._NORMA_ENDPOINT.format(id=norm_id)}"
        response = self._client.get(url, headers={"Accept": "application/xml"})
        response.raise_for_status()
        xml_bytes = response.content
        # Valida que sea XML bien formado antes de persistir
        etree.fromstring(xml_bytes)
        return xml_bytes

    def _ruta_xml_por_id(self, norm_id: str) -> Path:
        """Ruta estimada para idempotencia, sin parsear el XML (usa el ID)."""
        year = _year_from_id(norm_id)
        return self._cfg.raw_dir / year / f"{norm_id}.xml"

    def _persistir_error(self, norm_id: str, exc: Exception) -> None:
        """Guarda el error de descarga en ontology/kinetic-layer/api_boe/errors/{id}.json."""
        self._cfg.errors_dir.mkdir(parents=True, exist_ok=True)
        status_code: int | None = None
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code

        error_path = self._cfg.errors_dir / f"{norm_id}.json"
        payload = {
            "id": norm_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status_code": status_code,
            "error": str(exc),
            "attempts": 1,
        }
        error_path.write_text(json.dumps(payload, ensure_ascii=False))
        log.warning("Error persistido", id=norm_id, error=str(exc))


# ------------------------------------------------------------------ #
# Helpers de módulo                                                    #
# ------------------------------------------------------------------ #

_YEAR_RE = re.compile(r"-(\d{4})-")


def _year_from_id(norm_id: str) -> str:
    """Extrae el año de un ID tipo BOE-A-YYYY-NNNNN. Devuelve 'unknown' si no."""
    match = _YEAR_RE.search(norm_id)
    return match.group(1) if match else "unknown"
