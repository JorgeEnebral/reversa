# Reversa Founding Engineer - The Council of Ministers

Turn the Spanish *Boletín Oficial del Estado* into a knowledge graph and answer the four questions the Council of Ministers will actually ask: which laws have become unreadable, who made the mess, how much of the statute book rests on dead law, and what is the blast radius of the unfinished 2015 repeal.

Data is ingested from the [BOE open API](https://www.boe.es/datosabiertos) and modelled as a directed graph of amendments, repeals, and citations across the full consolidated-legislation corpus.

---

## Setup

**1. Install uv**

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Install dependencies**

```bash
uv sync
```

# 1. Java 21 (Neo4j 5 lo requiere)
sudo apt update
sudo apt install -y openjdk-21-jre-headless

# 2. Repo oficial de Neo4j
sudo mkdir -p /etc/apt/keyrings
wget -qO - https://debian.neo4j.com/neotechnology.gpg.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable 5' \
  | sudo tee /etc/apt/sources.list.d/neo4j.list

# 3. Instalar Neo4j Community 5
sudo apt update
sudo apt install -y neo4j

# 4. Contraseña inicial (sustituir <PASSWORD>)
sudo neo4j-admin dbms set-initial-password '<PASSWORD>'

# 5. Arrancar (en WSL no hay systemd por defecto; usar el servicio directo)
sudo service neo4j start
sudo service neo4j status     # debe mostrar "running"

# 6. Comprobar acceso
#    HTTP browser: http://localhost:7474  (usuario neo4j / contraseña anterior)
#    Bolt:         bolt://localhost:7687