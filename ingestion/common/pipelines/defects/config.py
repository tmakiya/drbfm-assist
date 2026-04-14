"""Configuration for defects pipeline."""

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


def _build_system_instruction(pipeline_dir: Path, prompt_file_path: Path | None = None) -> str:
    """Build system instruction from prompt template and config.

    Args:
        pipeline_dir: Directory containing config.yml
        prompt_file_path: Path to the prompt file. If None, uses DEFAULT_PROMPT_PATH.

    Returns:
        System instruction string with unit_list substituted

    """
    prompt_path = prompt_file_path
    prompt_template = prompt_path.read_text(encoding="utf-8").strip()

    config_path = pipeline_dir / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    unit_list_str = "\n".join(f"- {unit}" for unit in config["unit_list"])
    return prompt_template.replace("{{unit_list}}", unit_list_str)


@dataclass
class ImageAnalysisConfig:
    """Image analysis configuration."""

    model: str
    response_schema: dict[str, Any]
    system_instruction: str
    max_workers: int


@dataclass
class EmbeddingConfig:
    """Embedding configuration."""

    model: str
    source_field: str
    task_type: str
    dimensionality: int
    normalize: bool = False
    max_workers: int = 1


@dataclass
class IspConfig:
    """ISP ingestion configuration."""

    index_name: str
    id_field: str
    fields: dict[str, Any]
    mappings: dict[str, Any]
    settings: dict[str, Any]

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "IspConfig":
        """Create ISP config from full config dictionary."""
        isp_config = config.get("isp")
        if not isinstance(isp_config, dict):
            raise ValueError("'isp' not found in config")

        for key in ["index_name", "id_field", "fields", "mappings"]:
            if key not in isp_config:
                raise ValueError(f"'isp.{key}' not found in config")

        return cls(
            index_name=isp_config["index_name"],
            id_field=isp_config["id_field"],
            fields=isp_config["fields"],
            mappings=isp_config["mappings"],
            settings=isp_config.get("settings", {}),
        )


@dataclass
class PipelineConfig:
    """Defects pipeline configuration."""

    env: str
    tenant_id: str
    pipeline_dir: Path
    data_dir: Path
    config_path: Path
    image_analysis: ImageAnalysisConfig
    embedding: EmbeddingConfig
    isp: IspConfig
    bucket_name: str

    @classmethod
    def from_dir(cls, pipeline_dir: Path, prompt_file_path: Path | None = None) -> "PipelineConfig":
        """Create config from pipeline directory.

        Args:
            pipeline_dir: Directory containing config.yml
            prompt_file_path: Path to the prompt file.

        Returns:
            PipelineConfig instance

        """
        # Load environment config
        env_config = EnvironmentConfig.from_env()

        # Load config.yml
        config_path = pipeline_dir / "config.yml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if not isinstance(config_data, dict):
            raise ValueError("Config file must contain a mapping")

        # Image analysis config is required in config.yml
        image_analysis_config = config_data.get("image_analysis", {})
        if not image_analysis_config:
            raise ValueError("ImageAnalysis config must be configured in config.yml (image_analysis)")
        system_instruction = _build_system_instruction(pipeline_dir, prompt_file_path)

        image_analysis = ImageAnalysisConfig(
            model=image_analysis_config.get("model"),
            response_schema=image_analysis_config.get("response_schema"),
            system_instruction=system_instruction,
            max_workers=int(os.getenv("MAX_GEMINI_WORKERS", "3")),
        )

        # Embedding generation config is required in config.yml
        embedding_config = config_data.get("embedding_generation")
        if not embedding_config:
            raise ValueError("Embedding config must be configured in config.yml (embedding_generation)")
        embedding = EmbeddingConfig(
            model=embedding_config["model"],
            source_field=embedding_config["source_field"],
            task_type=embedding_config["task_type"],
            dimensionality=embedding_config["dimensionality"],
            normalize=embedding_config.get("normalize", False),
            max_workers=embedding_config.get("max_workers", 1),
        )

        # ISP config
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

        return cls(
            env=env_config.env,
            tenant_id=env_config.tenant_id,
            pipeline_dir=pipeline_dir,
            data_dir=pipeline_dir / "data",
            config_path=config_path,
            image_analysis=image_analysis,
            embedding=embedding,
            isp=isp,
            bucket_name=env_config.bucket_name,
        )
