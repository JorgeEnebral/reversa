# Reversa

Turn the Spanish *Boletín Oficial del Estado* (BOE) into a queryable knowledge graph and answer questions about the legal corpus through a conversational AI interface.

Data is ingested from the [BOE open API](https://www.boe.es/datosabiertos) and modelled as a directed graph of amendments, repeals, and citations across the full consolidated-legislation corpus. A web interface lets you explore the graph visually and query it in natural language.

---

## What it does

- **Ingests** consolidated legislation from the BOE open API and stores it in Neo4j.
- **Builds** a knowledge graph of legal relationships: `MODIFICA`, `DEROGA`, `CITA`.
- **Exposes** a web UI to explore the graph interactively — filter by node type, edge type, properties, and date range.
- **Answers** natural-language questions by generating Cypher queries via an LLM (Claude).
- **Traces** each answer back to source norms via `RESULT_EDGE` relationships stored in the graph.

---

## Setup

### 1. Install `uv`

```bash
# macOS / Linux / WSL
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install project dependencies

```bash
make install
```

### 3. Install Neo4j (Linux / WSL)

```bash
# Java 21 (required by Neo4j 5)
sudo apt update && sudo apt install -y openjdk-21-jre-headless

# Add the Neo4j official repo
sudo mkdir -p /etc/apt/keyrings
wget -qO - https://debian.neo4j.com/neotechnology.gpg.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable 5' \
  | sudo tee /etc/apt/sources.list.d/neo4j.list

# Install Neo4j Community 5
sudo apt update && sudo apt install -y neo4j

# Set the initial password (replace <PASSWORD> with your own)
sudo neo4j-admin dbms set-initial-password '<PASSWORD>'

# Start / stop / restart (WSL has no systemd — use the service command)
sudo service neo4j start
sudo service neo4j stop
sudo service neo4j restart
sudo service neo4j status
```

### 4. Configure environment variables

Create a `.env` file in the project root (`.env` is gitignored):

```dotenv
NEO4J__PASSWORD=your_password_here
LLM__ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Run

```bash
uv run python -m src.main
```

The web interface will be available at `http://localhost:8080`.

---

## Notebook demo

`src/pruebas.ipynb` contains a walkthrough of the ingestion pipeline, graph queries, and LLM integration.

---

## Architecture

See [`docs/architecture.pdf`](docs/architecture.pdf) for the full architecture diagram and [`docs/estructura_leyes.md`](docs/estructura_leyes.md) for the legal structure model.

---

## Project layout

```
src/
  api.py              # BOE API client
  preprocess.py       # Data ingestion pipeline
  llm.py              # LLM client (Claude + Cypher tool use)
  config.py           # Settings (Pydantic, validated at startup)
  semantic_schemas.py # Graph node/edge schemas
  web/                # NiceGUI web app (graph explorer + chat)
tests/                # pytest test suite (unit + integration)
ontology/             # Ontology definitions and ingested IDs
docs/                 # Architecture docs
```

---

## Development

```bash
make check    # ruff + mypy + pylint + complexipy
make test     # pytest with coverage (≥ 80% required)
make format   # auto-format with ruff
make all      # install + format + lint + test + clean
```
