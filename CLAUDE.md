# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a DRBFM (Design Review Based on Failure Mode) assist prototype that implements an LLM-powered search system for defect analysis and knowledge retrieval. The system uses LangGraph workflows, Elasticsearch for search, and Google Gemini for intelligent keyword extraction.

## Core Architecture

- **drassist/**: Main package containing the core functionality
  - **chains/**: LangGraph workflow implementations with base classes and search logic
  - **config/**: Configuration management for different environments
  - **elasticsearch/**: Elasticsearch client and query building
  - **embeddings/**: Azure OpenAI embeddings integration
  - **llm/**: Google Gemini client for structured content generation
- **configs/**: YAML configuration files for different deployments
- **scripts/**: Data ingestion and preprocessing utilities

## Key Components

1. **Search Workflow** (`drassist/chains/keyword_search.py`): 
   - LangGraph-based search pipeline with keyword extraction, Elasticsearch search, and fallback mechanisms
   - Uses BaseGraph pattern for modular workflow construction

2. **Configuration Management** (`drassist/config/manager.py`):
   - YAML-based configuration system supporting multiple environments

3. **Elasticsearch Integration** (`drassist/elasticsearch/manager.py`):
   - Advanced query building with MUST/SHOULD boolean logic
   - Japanese text analysis with kuromoji plugin

## Development Commands

```bash
# Install dependencies
uv sync

# Run main application
uv run python app.py

# Data ingestion
uv run python scripts/ingest.py

# Start Elasticsearch and Kibana services
docker-compose up -d elasticsearch kibana

# Code quality checks
pre-commit run --all-files
uv run ruff check .
uv ruff format .
```

## Configuration

- Uses environment-specific YAML configs in `configs/` directory
- Environment variables loaded from `.env` file
- Elasticsearch requires Japanese analysis plugins (kuromoji, icu)

## Testing and Quality

- Project uses pre-commit hooks for code quality
- Ruff for linting and formatting
- No specific test framework configured yet

## External Dependencies

- Google Gemini for LLM functionality via Vertex AI
- Azure OpenAI for embeddings
- Elasticsearch with Japanese text analysis
- Langfuse for workflow tracking and prompts