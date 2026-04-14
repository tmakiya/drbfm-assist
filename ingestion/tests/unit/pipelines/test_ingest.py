"""Unit tests for defects pipeline ingestion module."""

from pathlib import Path

import polars as pl
import pytest
import yaml
from common.isp.prepare_documents import prepare_documents
from common.pipelines.defects.config import IspConfig
from common.pipelines.defects.ingest import ingest_dataframe_to_isp
from common.utils.doc_id import hash_string_to_int64

# Import mock fixtures
from tests.mocks.isp_mock import MockISPResponse, MockISPSession, mock_isp_client  # noqa: F401


class TestHashStringToInt64:
    """Tests for hash_string_to_int64 function."""

    def test_hash_deterministic(self) -> None:
        """Test that same input produces same hash."""
        text = "test-string"

        hash1 = hash_string_to_int64(text)
        hash2 = hash_string_to_int64(text)

        assert hash1 == hash2

    def test_hash_different_inputs(self) -> None:
        """Test that different inputs produce different hashes."""
        hash1 = hash_string_to_int64("input1")
        hash2 = hash_string_to_int64("input2")

        assert hash1 != hash2

    def test_hash_is_int64(self) -> None:
        """Test that hash is within int64 range."""
        result = hash_string_to_int64("test")

        assert isinstance(result, int)
        # int64 range: -2^63 to 2^63-1
        assert -(2**63) <= result <= (2**63 - 1)

    def test_hash_unicode(self) -> None:
        """Test hashing with unicode characters."""
        result = hash_string_to_int64("日本語テスト")

        assert isinstance(result, int)


class TestIspConfig:
    """Tests for IspConfig."""

    def test_from_dict_success(self, temp_config_dir: Path) -> None:
        """Test successful ISP config parsing."""
        config_path = temp_config_dir / "config.yml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        isp_config = IspConfig.from_dict(config)

        assert isp_config.index_name == "test-defects"
        assert isp_config.id_field == "doc_id"
        assert "fields" in config["isp"]
        assert "mappings" in config["isp"]

    def test_from_dict_missing_isp_section(self) -> None:
        """Test error when isp section is missing."""
        config: dict[str, object] = {"other_section": {}}

        with pytest.raises(ValueError, match="'isp' not found in config"):
            IspConfig.from_dict(config)

    def test_from_dict_missing_fields(self) -> None:
        """Test error when required fields are missing."""
        config: dict[str, object] = {"isp": {"index_name": "test"}}

        with pytest.raises(ValueError, match="isp.id_field"):
            IspConfig.from_dict(config)


class TestPrepareDocuments:
    """Tests for prepare_documents function."""

    def test_prepare_documents_success(self) -> None:
        """Test successful document preparation."""
        df = pl.DataFrame(
            {
                "doc_id": [1, 2],
                "original_id": ["ORG001", "ORG002"],
                "cause_original": ["原因1", "原因2"],
                "cause_unit": ["ユニット1", "ユニット2"],
                "cause_part": [["部品A"], ["部品B"]],
                "unit_part_change": ["変更1", "変更2"],
                "failure_mode": ["摩耗", "破損"],
                "failure_effect": ["効果1", "効果2"],
                "countermeasures": ["対策1", "対策2"],
                "embedding": [[0.1] * 768, [0.2] * 768],
            }
        )

        field_config = {
            "doc_id": "doc_id",
            "original_id": "original_id",
            "cause": {
                "original": "cause_original",
                "unit": "cause_unit",
                "part": "cause_part",
                "part_change": "unit_part_change",
            },
            "failure": {
                "mode": "failure_mode",
                "effect": "failure_effect",
            },
            "countermeasures": "countermeasures",
        }

        documents = prepare_documents(df, field_config)

        assert len(documents) == 2
        assert documents[0]["original_id"] == "ORG001"
        assert documents[0]["cause"]["unit"] == "ユニット1"
        assert documents[0]["failure"]["mode"] == "摩耗"
        assert "embedding" in documents[0]

    def test_prepare_documents_without_embedding(self) -> None:
        """Test document preparation without embedding column."""
        df = pl.DataFrame(
            {
                "doc_id": [1],
                "original_id": ["ORG001"],
                "cause_original": ["原因1"],
                "cause_unit": ["ユニット1"],
                "cause_part": [["部品A"]],
                "unit_part_change": ["変更1"],
                "failure_mode": ["摩耗"],
                "failure_effect": ["効果1"],
                "countermeasures": ["対策1"],
            }
        )

        field_config = {
            "doc_id": "doc_id",
            "original_id": "original_id",
            "cause": {
                "original": "cause_original",
                "unit": "cause_unit",
                "part": "cause_part",
                "part_change": "unit_part_change",
            },
            "failure": {
                "mode": "failure_mode",
                "effect": "failure_effect",
            },
            "countermeasures": "countermeasures",
        }

        documents = prepare_documents(df, field_config)

        assert len(documents) == 1
        assert "embedding" not in documents[0]

    def test_prepare_documents_adds_chunk_fields(self) -> None:
        """Test document preparation adds chunk fields when present."""
        df = pl.DataFrame(
            {
                "doc_id": [1],
                "chunk_id": [0],
                "total_chunks": [3],
            }
        )

        field_config = {
            "doc_id": "doc_id",
        }

        documents = prepare_documents(df, field_config)

        assert len(documents) == 1
        assert documents[0]["chunk_id"] == 0
        assert documents[0]["total_chunks"] == 3

    def test_prepare_documents_uses_doc_id(self) -> None:
        """Test that doc_id is taken from the DataFrame."""
        df = pl.DataFrame(
            {
                "doc_id": [hash_string_to_int64("ORG001")],
                "original_id": ["ORG001"],
                "cause_original": [""],
                "cause_unit": [""],
                "cause_part": [[]],
                "unit_part_change": [""],
                "failure_mode": [""],
                "failure_effect": [""],
                "countermeasures": [""],
            }
        )

        field_config = {
            "doc_id": "doc_id",
            "original_id": "original_id",
            "cause": {
                "original": "cause_original",
                "unit": "cause_unit",
                "part": "cause_part",
                "part_change": "unit_part_change",
            },
            "failure": {
                "mode": "failure_mode",
                "effect": "failure_effect",
            },
            "countermeasures": "countermeasures",
        }

        documents = prepare_documents(df, field_config)

        assert documents[0]["doc_id"] == hash_string_to_int64("ORG001")


class TestIngestDataframeToISP:
    """Tests for ingest_dataframe_to_isp function."""

    def test_ingest_dry_run(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test dry run mode saves output without actual ingestion."""
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        df = pl.DataFrame(
            {
                "doc_id": [1],
                "original_id": ["ORG001"],
                "cause_original": ["原因1"],
                "cause_unit": ["ユニット1"],
                "cause_part": [["部品A"]],
                "unit_part_change": ["変更1"],
                "failure_mode": ["摩耗"],
                "failure_effect": ["効果1"],
                "countermeasures": ["対策1"],
            }
        )

        config = yaml.safe_load((temp_config_dir / "config.yml").read_text(encoding="utf-8"))
        isp_config = IspConfig.from_dict(config)
        result = ingest_dataframe_to_isp(
            df=df,
            isp_config=isp_config,
            pipeline_dir=temp_config_dir,
            dry_run=True,
        )

        assert result["total"] == 1
        assert result["success"] == 1
        assert result["errors"] == 0
        assert "test-tenant" in result["index_name"]

        # Check dry run output was created
        dry_run_dir = temp_config_dir / "dry_run_output"
        assert dry_run_dir.exists()

    def test_ingest_missing_tenant_id_raises(
        self,
        temp_config_dir: Path,
    ) -> None:
        """Test that missing TENANT_ID raises ValueError."""
        df = pl.DataFrame(
            {
                "doc_id": [1],
                "original_id": ["ORG001"],
            }
        )

        config = yaml.safe_load((temp_config_dir / "config.yml").read_text(encoding="utf-8"))
        isp_config = IspConfig.from_dict(config)
        with pytest.raises(ValueError, match="TENANT_ID"):
            ingest_dataframe_to_isp(
                df=df,
                isp_config=isp_config,
                pipeline_dir=temp_config_dir,
            )

    def test_ingest_success(
        self,
        temp_config_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test successful ingestion."""
        monkeypatch.setenv("TENANT_ID", "test-tenant")
        monkeypatch.setenv("LOCAL_MODE", "true")
        monkeypatch.setenv("ISP_API_URL", "http://localhost:3000")

        # Mock ISP client at the module level
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.health_check.return_value = {"status": "ok"}
        mock_client.index_exists.return_value = False
        mock_client.create_index.return_value = {"acknowledged": True}
        mock_client.bulk_index_documents.return_value = {
            "total": 2,
            "success": 2,
            "errors": 0,
        }

        with patch(
            "common.pipelines.defects.ingest.create_isp_client_from_env",
            return_value=mock_client,
        ):
            df = pl.DataFrame(
                {
                    "doc_id": [1, 2],
                    "original_id": ["ORG001", "ORG002"],
                    "cause_original": ["原因1", "原因2"],
                    "cause_unit": ["ユニット1", "ユニット2"],
                    "cause_part": [["部品A"], ["部品B"]],
                    "unit_part_change": ["変更1", "変更2"],
                    "failure_mode": ["摩耗", "破損"],
                    "failure_effect": ["効果1", "効果2"],
                    "countermeasures": ["対策1", "対策2"],
                }
            )

            config = yaml.safe_load((temp_config_dir / "config.yml").read_text(encoding="utf-8"))
            isp_config = IspConfig.from_dict(config)
            result = ingest_dataframe_to_isp(
                df=df,
                isp_config=isp_config,
                pipeline_dir=temp_config_dir,
            )

        assert result["total"] == 2
        assert result["success"] == 2
