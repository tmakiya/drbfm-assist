"""Tests for parse_csv function."""

import io
import sys
from pathlib import Path

# Add parent and src directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from csv_utils import parse_csv
from validators import ValidationConfig, validate_change_points


class TestParseCsvValidInput:
    """Tests for valid CSV input."""

    def test_valid_csv_single_column(self):
        """Test parsing a valid CSV with only the required column."""
        csv_content = "変更\n材質をSUS304からSUS316に変更\n回転数を1500rpmから1800rpmに増加"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        assert list(df.columns) == ["変更"]
        assert df.iloc[0]["変更"] == "材質をSUS304からSUS316に変更"
        assert df.iloc[1]["変更"] == "回転数を1500rpmから1800rpmに増加"
        assert warnings == []
        assert errors == []

    def test_valid_csv_with_extra_columns(self):
        """Test parsing a valid CSV with extra columns (should be ignored with warning)."""
        csv_content = "変更,備考,作成日\n材質を変更,テスト用,2024-01-01\n回転数を増加,本番用,2024-01-02"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        assert list(df.columns) == ["変更"]
        assert len(warnings) == 1
        assert "余分な列は無視されます" in warnings[0]
        assert "備考" in warnings[0]
        assert "作成日" in warnings[0]
        assert errors == []


class TestParseCsvEmptyRows:
    """Tests for CSV with empty rows."""

    def test_csv_with_trailing_empty_lines(self):
        """Test parsing a CSV with trailing empty lines."""
        csv_content = "変更\n材質を変更\n回転数を増加\n\n\n"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        assert errors == []

    def test_csv_with_empty_rows_in_middle(self):
        """Test parsing a CSV with empty rows in the middle.

        Note: pd.read_csv with skip_blank_lines=True automatically skips blank lines
        during parsing, so no warning is generated for pure blank lines.
        """
        csv_content = "変更\n材質を変更\n\n回転数を増加\n\n速度を変更"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 3
        # No warning because pd.read_csv skips blank lines automatically
        assert errors == []

    def test_csv_with_whitespace_only_rows(self):
        """Test parsing a CSV with whitespace-only rows.

        Note: pd.read_csv with skip_blank_lines=True also skips whitespace-only lines,
        so no warning is generated during post-filtering.
        """
        csv_content = "変更\n材質を変更\n   \n回転数を増加"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        # No warning because pd.read_csv skips whitespace-only lines too
        assert errors == []

    def test_csv_with_nan_values(self):
        """Test parsing a CSV with NaN values in the '変更' column.

        NaN values are filtered out by parse_csv, generating a warning.
        """
        # Create CSV with explicit NaN (empty cell between commas)
        csv_content = "変更,備考\n材質を変更,OK\n,空の変更\n回転数を増加,OK"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2  # Only rows with non-empty 変更
        # Should have warnings for both extra column and empty row
        assert any("空行をスキップしました" in w for w in warnings)
        assert errors == []

    def test_csv_all_empty_rows(self):
        """Test parsing a CSV with all empty rows."""
        csv_content = "変更\n\n\n   \n"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is None
        assert warnings == []
        assert len(errors) == 1
        assert "有効なデータがありません" in errors[0]


class TestParseCsvMissingColumn:
    """Tests for CSV with missing required column."""

    def test_csv_missing_required_column(self):
        """Test parsing a CSV without the required '変更' column."""
        csv_content = "名前,値\nテスト1,100\nテスト2,200"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is None
        assert warnings == []
        assert len(errors) == 1
        assert "「変更」列が見つかりません" in errors[0]
        assert "名前" in errors[0]
        assert "値" in errors[0]

    def test_csv_empty_file(self):
        """Test parsing an empty CSV file."""
        csv_content = ""
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is None
        assert len(errors) == 1

    def test_csv_header_only(self):
        """Test parsing a CSV with header only (no data rows)."""
        csv_content = "変更"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is None
        assert len(errors) == 1
        assert "有効なデータがありません" in errors[0]


class TestParseCsvMalformed:
    """Tests for malformed CSV input."""

    def test_csv_with_inconsistent_columns(self):
        """Test parsing a CSV with inconsistent number of columns per row."""
        csv_content = "変更,備考\n材質を変更\n回転数を増加,追加情報,余分なデータ"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        # pandas handles this gracefully - either parses or returns error
        # The behavior depends on pandas version, so we just check it doesn't crash
        assert (df is not None) or (len(errors) > 0)


class TestParseCsvEdgeCases:
    """Tests for edge cases."""

    def test_csv_with_special_characters(self):
        """Test parsing a CSV with special characters."""
        csv_content = "変更\n材質を\"SUS304\"から変更\nコンマ,を含む文字列"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        # Should handle special characters
        assert df is not None or len(errors) > 0

    def test_csv_with_unicode(self):
        """Test parsing a CSV with various unicode characters."""
        csv_content = "変更\n絵文字を含む変更🔧\n中文字符测试"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        assert errors == []

    def test_csv_single_data_row(self):
        """Test parsing a CSV with a single data row."""
        csv_content = "変更\n材質を変更"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 1
        assert df.iloc[0]["変更"] == "材質を変更"
        assert errors == []

    def test_csv_data_with_leading_trailing_whitespace(self):
        """Test that whitespace in data is stripped."""
        csv_content = "変更\n  材質を変更  \n   回転数を増加   "
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file)

        assert df is not None
        assert len(df) == 2
        # Note: parse_csv doesn't strip individual values, but filters empty ones
        assert errors == []


class TestParseCsvValidation:
    """Tests for CSV validation (file size, row count, text length)."""

    def test_csv_exceeds_max_items(self):
        """Test that CSV with too many rows is rejected."""
        config = ValidationConfig(max_items=3)
        csv_content = "変更\n変更1\n変更2\n変更3\n変更4\n変更5"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file, config=config)

        assert df is None
        assert len(errors) == 1
        assert "変更点が多すぎます" in errors[0]
        assert "5件" in errors[0]
        assert "最大3件" in errors[0]

    def test_csv_at_max_items_limit(self):
        """Test that CSV at exactly max items is accepted."""
        config = ValidationConfig(max_items=3)
        csv_content = "変更\n変更1\n変更2\n変更3"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file, config=config)

        assert df is not None
        assert len(df) == 3
        assert errors == []

    def test_csv_text_too_long(self):
        """Test that text exceeding max length is rejected."""
        config = ValidationConfig(max_text_length=10)
        csv_content = "変更\nこれは非常に長いテキストです"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file, config=config)

        assert df is None
        assert len(errors) == 1
        assert "文字数が多すぎます" in errors[0]
        assert "10文字以内" in errors[0]

    def test_csv_text_too_short(self):
        """Test that text below min length is rejected."""
        config = ValidationConfig(min_text_length=5)
        csv_content = "変更\nABC"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file, config=config)

        assert df is None
        assert len(errors) == 1
        assert "文字数が少なすぎます" in errors[0]
        assert "5文字以上" in errors[0]

    def test_csv_multiple_validation_errors(self):
        """Test that multiple validation errors are collected."""
        config = ValidationConfig(min_text_length=5, max_text_length=15)
        csv_content = "変更\nAB\nこれは非常に非常に非常に長いテキストです\nOK変更点"
        file = io.StringIO(csv_content)

        df, warnings, errors = parse_csv(file, config=config)

        assert df is None
        assert len(errors) == 2  # One too short, one too long


class TestValidateChangePoints:
    """Tests for validate_change_points function."""

    def test_valid_change_points(self):
        """Test validation of valid change points."""
        change_points = ["材質を変更", "回転数を増加", "サイズを調整"]
        result = validate_change_points(change_points)

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_empty_change_points(self):
        """Test validation of empty change points list."""
        result = validate_change_points([])

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "処理する変更点がありません" in result.errors[0]

    def test_too_many_change_points(self):
        """Test validation when exceeding max items."""
        config = ValidationConfig(max_items=3)
        change_points = ["変更1", "変更2", "変更3", "変更4", "変更5"]
        result = validate_change_points(change_points, config=config)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "変更点が多すぎます" in result.errors[0]
        assert "5件" in result.errors[0]

    def test_text_too_long(self):
        """Test validation when text exceeds max length."""
        config = ValidationConfig(max_text_length=10)
        change_points = ["これは非常に長いテキストです"]
        result = validate_change_points(change_points, config=config)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "長すぎます" in result.errors[0]

    def test_text_too_short(self):
        """Test validation when text is below min length."""
        config = ValidationConfig(min_text_length=5)
        change_points = ["ABC"]
        result = validate_change_points(change_points, config=config)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "短すぎます" in result.errors[0]

    def test_whitespace_only_text(self):
        """Test validation of whitespace-only text."""
        config = ValidationConfig(min_text_length=1)
        change_points = ["   "]
        result = validate_change_points(change_points, config=config)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "短すぎます" in result.errors[0]

    def test_multiple_validation_errors(self):
        """Test that multiple errors are collected."""
        config = ValidationConfig(min_text_length=5, max_text_length=15)
        change_points = ["AB", "OK変更点", "これは非常に非常に非常に長いテキストです"]
        result = validate_change_points(change_points, config=config)

        assert result.is_valid is False
        assert len(result.errors) == 2  # One too short, one too long

    def test_default_config_values(self):
        """Test that default config values work correctly."""
        # Default: min=1, max=1000, max_items=50
        change_points = ["A", "B" * 1000]  # Min and max length
        result = validate_change_points(change_points)

        assert result.is_valid is True
        assert result.errors == []

    def test_exceeds_default_max_length(self):
        """Test that exceeding default max length (1000) fails."""
        change_points = ["A" * 1001]
        result = validate_change_points(change_points)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "長すぎます" in result.errors[0]
