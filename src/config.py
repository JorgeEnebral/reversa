"""
Configuración centralizada de Reversa.

APIConfig/API_CONFIG se mantienen para src/api.py
Settings agrega la configuración de Hitos 2-4: preprocesado, Neo4j, LLM y ontología.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repositorio (reversa/). Ancla las rutas de la ontología de forma
# absoluta para que resuelvan igual sea cual sea el directorio de trabajo.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Hito 1: API
# --------------------------------------------------------------------------- #


class APIConfig(BaseSettings):
    """Endpoints y rutas de persistencia de la API del BOE."""

    base_url: str = "https://www.boe.es/datosabiertos/api"
    timeout: int = 30
    wait: float = 0.0
    ontology_dir: Path = PROJECT_ROOT / "ontology/kinetic-layer/api_boe"

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


# --------------------------------------------------------------------------- #
# Hito 2: Preprocesado — flags de parseo                                      #
# --------------------------------------------------------------------------- #


class PreprocessConfig(BaseModel):
    """Rutas de la ontología. semantic-layer se regenera; dynamic-layer no."""

    ontology_dir: Path = PROJECT_ROOT / "ontology"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def semantic_subdir(self) -> Path:
        """Subdirectorio semantic-layer."""
        return self.ontology_dir / "semantic-layer"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def kinetic_subdir(self) -> Path:
        """Subdirectorio kinetic-layer."""
        return self.ontology_dir / "kinetic-layer"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dynamic_subdir(self) -> Path:
        """Subdirectorio dynamic-layer."""
        return self.ontology_dir / "dynamic-layer"

    @property
    def errors_dir(self) -> Path:
        """Directorio de errores de descarga."""
        return self.kinetic_subdir / "preprocess" / "errors"


class MetadatosFlags(BaseModel):
    """Controla qué campos de <metadatos> se extraen al modelo Norma.

    Todos los True por defecto salvo los que no alimentan ningún briefing.
    Los tres estatus (derogacion, anulacion, vigencia_agotada) se combinan
    para calcular el campo derivado `vigente` del nodo Neo4j.
    """

    id: bool = True
    fecha_actualizacion: bool = False
    ambito: bool = False
    departamento: bool = False
    rango: bool = True
    fecha_disposicion: bool = True
    numero_oficial: bool = True
    titulo: bool = True
    diario: bool = False
    fecha_publicacion: bool = True
    diario_numero: bool = False
    fecha_vigencia: bool = True
    estatus_derogacion: bool = True
    fecha_derogacion: bool = True
    estatus_anulacion: bool = True
    fecha_anulacion: bool = True
    vigencia_agotada: bool = True
    estado_consolidacion: bool = True
    url_eli: bool = False
    url_html_consolidada: bool = False


class AnalisisFlags(BaseModel):
    """Controla qué campos de <analisis> se extraen.

    referencias_anteriores y referencias_posteriores materializan aristas Neo4j.
    Anteriores: aristas donde la norma actual es el origen (norma → ref).
    Posteriores: solo cuando el origen no está en raw/ — evita duplicados y
    recupera aristas cuyo origen no tiene fichero propio en el corpus.
    """

    materias: bool = False
    notas: bool = False
    referencias_anteriores: bool = True
    referencias_posteriores: bool = True


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

    Los 3 códigos cubren los 4 briefings del Consejo. Los 47 restantes
    del catálogo BOE se ignoran.
    """

    codigos_a_relacion: dict[int, str] = {
        210: "DEROGA",
        270: "MODIFICA",
        330: "CITA",
    }


class Neo4jConfig(BaseModel):
    """Conexión a Neo4j. Credenciales cargadas desde .env vía Settings."""

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""  # sobreescribir con NEO4J__PASSWORD en .env
    database: str = "neo4j"


# --------------------------------------------------------------------------- #
# Hito 3: LLM                                                                 #
# --------------------------------------------------------------------------- #


class LLMConfig(BaseModel):
    """Config del cliente Anthropic. Credenciales y parámetros de comportamiento."""

    anthropic_api_key: str = ""  # requerido: LLM__ANTHROPIC_API_KEY en .env
    model: str = "claude-haiku-4-5"
    max_tokens: int = 2_000
    temperature: float = 0.0
    max_exchanges: int = (
        1  # Nº de exchanges completos (user→tools→answer) en el historial deslizante
    )


class WebConfig(BaseModel):
    """Config del servidor NiceGUI."""

    host: str = "127.0.0.1"
    port: int = 8080
    title: str = "Reversa"


# --------------------------------------------------------------------------- #
# Settings global                                                              #
# --------------------------------------------------------------------------- #


class Settings(BaseSettings):
    """Configuración global. Cargada desde .env con prefijo doble-guión bajo.

    Secretos requeridos en .env (startup falla si faltan):
        LLM__ANTHROPIC_API_KEY=sk-ant-...
        NEO4J__PASSWORD=mysecret

    Opcionales con defaults:
        NEO4J__URI=bolt://localhost:7687
        NEO4J__USER=neo4j
        NEO4J__DATABASE=reversa

    Attributes:
        parse: flags de parseo XML.
        relacion: codigos de relación a materializar como aristas.
        neo4j: conexión Neo4j.
        llm: parámetros del LLM (incluye anthropic_api_key).
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        frozen=True,
        extra="ignore",
    )

    api: APIConfig = APIConfig()
    preprocess: PreprocessConfig = PreprocessConfig()
    parse: ParseFlags = ParseFlags()
    relacion: RelacionConfig = RelacionConfig()
    neo4j: Neo4jConfig = Neo4jConfig()
    llm: LLMConfig = LLMConfig()
    web: WebConfig = WebConfig()

    @model_validator(mode="after")
    def _check_secrets(self) -> Settings:
        """Falla en startup si faltan secretos requeridos."""
        if not self.llm.anthropic_api_key:
            raise ValueError("LLM__ANTHROPIC_API_KEY es requerido en .env")
        if not self.neo4j.password:
            raise ValueError("NEO4J__PASSWORD es requerido en .env")
        return self


load_dotenv()
settings = Settings()
