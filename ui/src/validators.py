"""Validation utilities for DRBFM UI input."""

from dataclasses import dataclass


@dataclass
class ValidationConfig:
    """バリデーション設定"""

    min_text_length: int = 1
    max_text_length: int = 1000
    max_items: int = 50
    max_file_size_bytes: int = 1 * 1024 * 1024  # 1MB


@dataclass
class ValidationResult:
    """バリデーション結果"""

    is_valid: bool
    errors: list[str]
    warnings: list[str]


def validate_change_points(
    change_points: list[str],
    config: ValidationConfig = ValidationConfig(),
) -> ValidationResult:
    """変更点リストをバリデーション"""
    errors = []
    warnings = []

    # 件数チェック
    if len(change_points) == 0:
        errors.append("処理する変更点がありません")
    elif len(change_points) > config.max_items:
        errors.append(
            f"変更点が多すぎます（{len(change_points)}件）。最大{config.max_items}件まで入力できます"
        )

    # 各変更点の文字数チェック
    for i, cp in enumerate(change_points, 1):
        text_len = len(cp.strip())
        if text_len < config.min_text_length:
            errors.append(
                f"変更点 #{i} が短すぎます（{text_len}文字）。"
                f"{config.min_text_length}文字以上で入力してください"
            )
        elif text_len > config.max_text_length:
            errors.append(
                f"変更点 #{i} が長すぎます（{text_len}文字）。"
                f"{config.max_text_length}文字以内で入力してください"
            )

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
