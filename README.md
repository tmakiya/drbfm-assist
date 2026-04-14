# DRBFM Assist Prototype

This is a DRBFM (Design Review Based on Failure Mode) assist prototype that implements an LLM-powered search system for defect analysis and knowledge retrieval. The system uses LangGraph workflows, Elasticsearch for search, and Google Gemini for intelligent keyword extraction.

## Quick Start

For quick setup and deployment, see [QUICKSTART.md](./QUICKSTART.md).

For detailed deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## Architecture

The system is divided into two main components:

### Backend (`backend/`)
LangGraph API server that runs the DRBFM workflows:
- **drassist/**: Core DRBFM workflow logic
  - **chains/**: LangGraph workflow implementations
  - **config/**: Configuration management
  - **elasticsearch/**: Elasticsearch client and query building
  - **embeddings/**: Azure OpenAI embeddings integration
  - **llm/**: Google Gemini client for structured content generation
- **configs/**: YAML configuration files
- **langgraph.json**: LangGraph API configuration

### Frontend (`ui/`)
Streamlit-based web interface:
- **app.py**: Main Streamlit application (Tadano version)
- **app_ebara.py**: Ebara-specific version

### Infrastructure
- **Elasticsearch**: Search engine with Japanese text analysis
- **Kibana**: Elasticsearch visualization tool

## Prerequisites

### For Docker Deployment (Recommended)
- Docker and Docker Compose
- LangGraph CLI: `pip install langgraph-cli`
- Google Cloud credentials

### For Local Development
- Python 3.10 or higher
- uv package manager
- Docker and Docker Compose (for Elasticsearch)

## Setup Instructions

### Docker Deployment

See [QUICKSTART.md](./QUICKSTART.md) for step-by-step instructions.

Quick summary:
```bash
# 1. Setup backend environment
cd backend && cp .env.example .env
# Edit .env with your credentials

# 2. Generate backend Dockerfile
langgraph dockerfile ./Dockerfile

# 3. Start all services
docker-compose up -d
```

Access the UI at http://localhost:8501

### Local Development

#### 1. Install Dependencies

```bash
uv sync
```

#### 2. Start Infrastructure Services

```bash
docker-compose up -d elasticsearch kibana
```

#### 3. Environment Variables

Create a `.env` file in the backend directory:

```bash
cd backend
cp .env.example .env
# Edit .env with your configuration
```

#### 4. Run Backend (Development Mode)

```bash
cd backend
langgraph dev
```

Backend will be available at http://localhost:8123

#### 5. Run UI (Development Mode)

In a separate terminal:

```bash
cd ui
streamlit run app.py
```

UI will be available at http://localhost:8501

### Data Setup

#### Preprocess Data

Place the original data in `data/6307204b/AQOS.csv` and run:

```bash
uv run poe preprocess_6307204b
```

#### Data Ingestion

```bash
uv run python -m scripts.ingest configs/6307204b.yaml
```

## Development

### Code Quality Checks

```bash
# Install pre-commit hooks
uv run pre-commit install

# Linting
uv run ruff check .

# Formatting
uv run ruff format .
```

## External Dependencies

- Google Gemini for LLM functionality via Vertex AI
- Azure OpenAI for embeddings
- Elasticsearch with Japanese text analysis
- Langfuse for workflow tracking and prompts