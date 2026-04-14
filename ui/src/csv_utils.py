"""CSV parsing utilities for DRBFM UI."""

import pandas as pd

try:
    from .validators import ValidationConfig
except ImportError:
    from validators import ValidationConfig


def parse_csv(
    uploaded_file,
    config: ValidationConfig = ValidationConfig(),
) -> tuple[pd.DataFrame | None, list[str], list[str]]:
    """Parse CSV file with validation and return cleaned DataFrame.

    Returns:
        (DataFrame or None, warnings, errors)
        - warnings: toastで表示する警告（空行スキップ、余分カラムなど）
        - errors: st.error()で表示するエラー（CSVパースエラーなど）
    """
    warnings = []
    errors = []

    # ファイルサイズチェック
    if hasattr(uploaded_file, "size") and uploaded_file.size > config.max_file_size_bytes:
        size_mb = uploaded_file.size / (1024 * 1024)
        max_mb = config.max_file_size_bytes / (1024 * 1024)
        return None, [], [
            f"ファイルサイズが大きすぎます（{size_mb:.1f}MB）。"
            f"{max_mb:.0f}MB以下のファイルをアップロードしてください"
        ]

    try:
        df = pd.read_csv(uploaded_file, on_bad_lines="warn", skip_blank_lines=True)
    except pd.errors.ParserError as e:
        return None, [], [f"CSVの解析に失敗しました: {e}"]
    except Exception as e:
        return None, [], [f"ファイルの読み込みに失敗しました: {e}"]

    # 必須カラム確認
    if "変更" not in df.columns:
        return None, [], [f"「変更」列が見つかりません。現在の列: {', '.join(df.columns)}"]

    # 余分なカラムチェック（警告）
    extra_cols = [col for col in df.columns if col != "変更"]
    if extra_cols:
        warnings.append(f"余分な列は無視されます: {', '.join(extra_cols)}")

    # 「変更」列のみ抽出
    df = df[["変更"]].copy()

    # 空行フィルタリング（警告）
    original_len = len(df)
    df = df.dropna(subset=["変更"])
    df = df[df["変更"].astype(str).str.strip() != ""]
    filtered_len = len(df)

    if original_len > filtered_len:
        skipped = original_len - filtered_len
        warnings.append(f"{skipped}行の空行をスキップしました")

    if len(df) == 0:
        return None, [], ["有効なデータがありません"]

    # 行数チェック
    if len(df) > config.max_items:
        errors.append(
            f"変更点が多すぎます（{len(df)}件）。最大{config.max_items}件まで入力できます"
        )
        return None, warnings, errors

    # 各行の文字数チェック
    for idx, row in df.iterrows():
        text = str(row["変更"]).strip()
        text_len = len(text)
        row_num = idx + 1  # 1-indexed for user display

        if text_len < config.min_text_length:
            errors.append(
                f"行 {row_num}: 文字数が少なすぎます（{text_len}文字）。"
                f"{config.min_text_length}文字以上で入力してください"
            )
        elif text_len > config.max_text_length:
            errors.append(
                f"行 {row_num}: 文字数が多すぎます（{text_len}文字）。"
                f"{config.max_text_length}文字以内で入力してください"
            )

    if errors:
        return None, warnings, errors

    return df, warnings, []
