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