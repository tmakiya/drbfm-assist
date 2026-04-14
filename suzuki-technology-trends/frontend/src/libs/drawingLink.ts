/**
 * drawing_id リンク変換ユーティリティ
 *
 * drawing_id（図面番号）をCADDi Drawerへのリンクに変換する機能を提供
 */

import { escapeHtml } from './sanitize';

/**
 * drawing_idの正規表現パターン
 * 形式: DR-[A-Z0-9]+ (例: DR-OJOBBMHKFDHN, DR-NEANC3YYM7L3)
 */
const DRAWING_ID_PATTERN = /DR-[A-Z0-9]+/g;

/**
 * 既にMarkdownリンク内にあるパターンを除外するための正規表現
 * [DR-XXX](url) や既存リンク内のdrawing_idを二重変換しない
 */
const DRAWING_ID_NOT_IN_LINK_PATTERN = /(?<!\[)DR-[A-Z0-9]+(?!\]|\()/g;

/**
 * URLのパスからtenant_idを抽出
 *
 * パス形式: /alpha-agents/{tenant_id}/suzuki-technology-trends
 *
 * @returns tenant_id (UUID形式) または null
 */
export function getTenantIdFromPath(): string | null {
  if (typeof window === 'undefined') return null;

  const uuidPattern = /\/alpha-agents\/([0-9a-f-]{36})\//i;
  const match = window.location.pathname.match(uuidPattern);
  return match ? match[1] : null;
}

/**
 * drawing_id から CADDi Drawer へのURLを生成
 *
 * @param drawingId - 図面番号 (例: DR-OJOBBMHKFDHN)
 * @param tenantId - テナントID (UUID)
 * @returns Drawer URLまたはnull (tenant_idがない場合)
 */
export function buildDrawerUrl(drawingId: string, tenantId: string | null): string | null {
  if (!drawingId || !tenantId) return null;

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
  return `${baseUrl}/${tenantId}?t=id&q=${encodeURIComponent(drawingId)}&focusViewMode=detail`;
}

/**
 * Markdown文字列内のdrawing_idをリンク形式に変換
 *
 * 変換例:
 *   "DR-OJOBBMHKFDHN を参照" → "[DR-OJOBBMHKFDHN](https://...)"
 *
 * 既にリンク形式になっているdrawing_idは変換しない
 *
 * @param markdown - 変換対象のMarkdown文字列
 * @param tenantId - テナントID
 * @returns drawing_idがリンク化されたMarkdown文字列
 */
export function convertDrawingIdsToMarkdownLinks(
  markdown: string,
  tenantId: string | null
): string {
  if (!markdown || !tenantId) return markdown;

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';

  return markdown.replace(DRAWING_ID_NOT_IN_LINK_PATTERN, (match) => {
    const url = `${baseUrl}/${tenantId}?t=id&q=${encodeURIComponent(match)}&focusViewMode=detail`;
    return `[${match}](${url})`;
  });
}

/**
 * HTML文字列内のdrawing_idをリンク形式に変換（HTMLダウンロード用）
 *
 * @param text - 変換対象の文字列（プレーンテキスト）
 * @param tenantId - テナントID
 * @returns drawing_idがHTMLリンクに変換された文字列
 */
export function convertDrawingIdsToHtmlLinks(text: string, tenantId: string | null): string {
  if (!text || !tenantId) return text;

  const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';

  return text.replace(DRAWING_ID_PATTERN, (match) => {
    const url = `${baseUrl}/${tenantId}?t=id&q=${encodeURIComponent(match)}&focusViewMode=detail`;
    return `<a href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(match)}</a>`;
  });
}

/**
 * drawing_idかどうかを判定
 *
 * @param value - 判定対象の文字列
 * @returns drawing_idの形式にマッチするかどうか
 */
export function isDrawingId(value: string | null | undefined): boolean {
  if (!value) return false;
  return /^DR-[A-Z0-9]+$/.test(value);
}
