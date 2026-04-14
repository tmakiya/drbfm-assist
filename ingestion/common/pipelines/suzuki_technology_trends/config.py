"""Configuration helpers for the Suzuki Technology Trends pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EnvironmentConfig:
    """Environment-specific configuration."""

    env: str
    tenant_id: str
    project_id: str
    bucket_name: str

    @classmethod
    def from_env(cls) -> "EnvironmentConfig":
        """Create config from ENV environment variable."""
        env = os.getenv("ENV")
        tenant_id = os.getenv("TENANT_ID")

        # Map environment to GCP project ID
        project_map = {
            "dev": "zoolake-dev",
            "stg": "zoolake-stg-e3979",
            "prod": "zoolake-prod",
            "test": "zoolake-test",
        }
        if env not in project_map:
            raise ValueError(f"Unknown environment: {env}")
        project_id = project_map[env]

        return cls(
            env=env,
            tenant_id=tenant_id,
            project_id=project_id,
            bucket_name=f"{project_id}.appspot.com",
        )


@dataclass(frozen=True)
class EmbeddingConfig:
    """Embedding generation settings."""

    model: str
    source_field: str
    task_type: str
    dimensionality: int
    normalize: bool = False
    max_workers: int = 1


@dataclass(frozen=True)
class IspConfig:
    """ISP ingestion settings."""

    index_name: str
    id_field: str
    fields: dict[str, Any]
    mappings: dict[str, Any]
    settings: dict[str, Any]


@dataclass(frozen=True)
class PipelineConfig:
    """Pipeline configuration for Suzuki Technology Trends."""

    env: str
    tenant_id: str
    pipeline_dir: Path
    data_dir: Path
    config_path: Path
    embedding: EmbeddingConfig
    isp: IspConfig
    bq_project: str
    table_fqn: str
    batch_size: int
    chunk_size: int
    chunk_overlap: int

    @classmethod
    def from_dir(cls, pipeline_dir: Path) -> "PipelineConfig":
        """Create config from a pipeline directory."""
        # Load environment config
        env_config = EnvironmentConfig.from_env()

        # load config from file
        config_path = pipeline_dir / "config.yml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if not isinstance(config_data, dict):
            raise ValueError("Config file must contain a mapping")

        # load batch processing config
        batch_config = config_data.get("batch_processing")
        if not isinstance(batch_config, dict) or "batch_size" not in batch_config:
            raise ValueError("'batch_processing.batch_size' not found in config")
        batch_size = int(batch_config["batch_size"])
        if batch_size <= 0:
            raise ValueError("'batch_processing.batch_size' must be greater than 0")

        # load chunking config
        chunk_config = config_data.get("chunking", {})
        if not isinstance(chunk_config, dict):
            raise ValueError("Chunking config must be a mapping in config.yml (chunking)")

        chunk_size = int(chunk_config.get("chunk_size"))
        chunk_overlap = int(chunk_config.get("chunk_overlap"))

        if chunk_size <= 0:
            raise ValueError("'chunking.chunk_size' must be greater than 0")
        if chunk_overlap < 0:
            raise ValueError("'chunking.chunk_overlap' must be non-negative")

        # load embedding config
        embedding_config = config_data.get("embedding_generation")
        if not isinstance(embedding_config, dict):
            raise ValueError("Embedding config must be configured in config.yml (embedding_generation)")
        for key in ["model", "source_field", "task_type"]:
            if key not in embedding_config:
                raise ValueError(f"'embedding_generation.{key}' not found in config")

        embedding = EmbeddingConfig(
            model=embedding_config["model"],
            source_field=embedding_config["source_field"],
            task_type=embedding_config["task_type"],
            dimensionality=int(embedding_config.get("dimensionality", 768)),
            normalize=embedding_config.get("normalize", False),
            max_workers=int(embedding_config.get("max_workers", 1)),
        )

        # load ISP config
        isp_config = config_data.get("isp")
        if not isinstance(isp_config, dict):
            raise ValueError("'isp' not found in config")
        for key in ["index_name", "id_field", "fields", "mappings"]:
            if key not in isp_config:
                raise ValueError(f"'isp.{key}' not found in config")

        isp = IspConfig(
            index_name=isp_config["index_name"],
            id_field=isp_config["id_field"],
            fields=isp_config["fields"],
            mappings=isp_config["mappings"],
            settings=isp_config.get("settings", {}),
        )

        # build table FQN
        esperanto_project = f"esperanto-drawer-{env_config.env.lower()}"
        tenant_id_formatted = env_config.tenant_id.replace("-", "_")
        tenant_dataset = f"tenant_{tenant_id_formatted}"
        table_fqn = f"{esperanto_project}.{tenant_dataset}.solution_technology_trends_input"

        return cls(
            env=env_config.env,
            tenant_id=env_config.tenant_id,
            pipeline_dir=pipeline_dir,
            data_dir=pipeline_dir / "data",
            config_path=config_path,
            bq_project=esperanto_project,
            table_fqn=table_fqn,
            batch_size=batch_size,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding=embedding,
            isp=isp,
        )
