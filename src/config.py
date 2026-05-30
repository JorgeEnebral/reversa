"""
Configuración centralizada de Reversa.

APIConfig/API_CONFIG se mantienen para src/api.py (Hito 1, ya implementado).
Settings agrega la configuración de Hitos 2-4: preprocesado, Neo4j, LLM y ontología.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


# --------------------------------------------------------------------------- #
# Hito 1: API
# --------------------------------------------------------------------------- #


class APIConfig(BaseSettings):
    """Endpoints y rutas de persistencia de la API del BOE."""

    base_url: str = "https://www.boe.es/datosabiertos/api"
    timeout: int = 30
    wait: float = 0.0
    ontology_dir: Path = Path("ontology/kinetic-layer/api_boe")

    @property
    def raw_dir(self) -> Path:
        """Directorio de XMLs descargados."""
        return self.ontology_dir / "raw"

    @property
    def errors_dir(self) -> Path:
        """Directorio de errores de descarga."""
        return self.ontology_dir / "errors"

    @property
    def ids_file(self) -> Path:
        """Fichero con el listado de IDs."""
        return self.ontology_dir / "ids.txt"

    model_config = {"frozen": True}


API_CONFIG = APIConfig()


# --------------------------------------------------------------------------- #
# Hito 2: Preprocesado — flags de parseo                                      #
# --------------------------------------------------------------------------- #


class PreprocessConfig(BaseModel):
    """Rutas de la ontología. semantic-layer se regenera; dynamic-layer no."""

    ontology_dir: Path = Path("ontology")
    semantic_subdir: str = "semantic-layer"
    kinetic_subdir: str = "kinetic-layer"
    dynamic_subdir: str = "dynamic-layer"
    
    @property
    def errors_dir(self) -> Path:
        """Directorio de errores de descarga."""
        return self.ontology_dir / self.kinetic_subdir / "preprocess" / "errors"
    

class MetadatosFlags(BaseModel):
    """Controla qué campos de <metadatos> se extraen al modelo Norma.

    Todos los True por defecto salvo los que no alimentan ningún briefing.
    Los tres estatus (derogacion, anulacion, vigencia_agotada) se combinan
    para calcular el campo derivado `vigente` del nodo Neo4j.
    """
    
    id: bool = True
    fecha_actualizacion: bool = True
    ambito: bool = True
    departamento: bool = True
    rango: bool = True
    fecha_disposicion: bool = True
    numero_oficial: bool = False
    titulo: bool = True
    diario: bool = True
    fecha_publicacion: bool = True
    diario_numero: bool = False
    fecha_vigencia: bool = True
    estatus_derogacion: bool = True
    fecha_derogacion: bool = False
    estatus_anulacion: bool = True
    fecha_anulacion: bool = False
    vigencia_agotada: bool = True
    estado_consolidacion: bool = False
    url_eli: bool = False
    url_html_consolidada: bool = False


class AnalisisFlags(BaseModel):
    """Controla qué campos de <analisis> se extraen.

    Solo referencias_anteriores alimenta aristas en el grafo.
    referencias_posteriores se omite: es redundante (cada relación aparece
    en <anteriores> del actor y en <posteriores> del receptor).
    """

    materias: bool = True
    notas: bool = False
    referencias_anteriores: bool = True


class MetadataEliFlags(BaseModel):
    """Estructura reservada para <metadata-eli>. Sin campos por ahora."""


class TextoFlags(BaseModel):
    """Estructura reservada para <texto>. Sin campos por ahora."""


class ParseFlags(BaseModel):
    """Combina los cuatro bloques raíz del XML BOE.

    Regla en cascada: si un bloque es False (bool), se ignora entero.
    Si es un sub-modelo, solo se parsean los hijos con True.
    metadata_eli y texto se reservan para uso futuro (False por defecto).
    """

    metadatos: MetadatosFlags | bool = MetadatosFlags()
    analisis: AnalisisFlags | bool = AnalisisFlags()
    metadata_eli: MetadataEliFlags | bool = False
    texto: TextoFlags | bool = False


class RelacionConfig(BaseModel):
    """Mapeo codigo_relacion → TYPE Cypher.

    Los 20 códigos cubren los 4 briefings del Consejo. Los ~33 restantes
    del catálogo BOE (correcciones, recursos TC, anulaciones...) se ignoran.
    """

    codigos_a_relacion: dict[int, str] = {
        210: "DEROGA",
        211: "DEROGA_LO_INDICADO",
        212: "DEROGA_CON_EXCEPCION",
        213: "DEROGA_EN_CUANTO_SE_OPONGA",
        214: "DEROGA_EN_FORMA_INDICADA",
        215: "DEROGA_PARCIALMENTE",
        216: "DEROGA_REITERADA",
        217: "DEROGA_TACITAMENTE",
        270: "MODIFICA",
        271: "MODIFICA_PLAN",
        272: "MODIFICA_DET",
        235: "SUPRIME",
        245: "SUSTITUYE",
        407: "AÑADE",
        330: "CITA",
        331: "EN_RELACION_CON",
        490: "DESARROLLA",
        420: "APRUEBA",
        426: "TRANSPONE",
        427: "TRANSPONE_PARCIALMENTE",
    }


class Neo4jConfig(BaseModel):
    """Conexión a Neo4j. NEO4J__PASSWORD se carga desde .env vía Settings."""

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""
    database: str = "reversa"


# --------------------------------------------------------------------------- #
# Hito 3: LLM                                                                 #
# --------------------------------------------------------------------------- #


class LLMConfig(BaseModel):
    """Config del cliente Anthropic. ANTHROPIC_API_KEY se lee en src/llm.py."""

    model: str = "claude-haiku-4-5"
    max_tokens: int = 4000
    temperature: float = 0.2


# --------------------------------------------------------------------------- #
# Settings global                                                              #
# --------------------------------------------------------------------------- #


class Settings(BaseSettings):
    """Configuración global. Cargada desde .env con prefijo doble-guión bajo.

    Ejemplo de .env:
        NEO4J__URI=bolt://localhost:7687
        NEO4J__USER=neo4j
        NEO4J__PASSWORD=mysecret
        NEO4J__DATABASE=reversa

    Attributes:
        parse: flags de parseo XML.
        relacion: codigos de relación a materializar como aristas.
        neo4j: conexión Neo4j.
        ontology: rutas de la ontología.
        llm: parámetros del LLM.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        frozen=True,
    )

    api: APIConfig = APIConfig()
    preprocess: PreprocessConfig = PreprocessConfig()
    parse: ParseFlags = ParseFlags()
    relacion: RelacionConfig = RelacionConfig()
    neo4j: Neo4jConfig = Neo4jConfig()
    llm: LLMConfig = LLMConfig()


load_dotenv()
settings = Settings()
