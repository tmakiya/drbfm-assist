/**
 * サニタイズユーティリティ
 *
 * XSS対策、プロンプトインジェクション対策、入力検証のための関数群
 */

/**
 * HTMLエスケープ（XSS対策）
 *
 * HTMLの特殊文字をエンティティに変換し、XSS攻撃を防止する
 */
export function escapeHtml(str: string): string {
  if (!str) return '';

  const htmlEntities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
    '`': '&#x60;',
  };

  return str.replace(/[&<>"'`/]/g, (char) => htmlEntities[char] || char);
}

/**
 * プロンプトインジェクション対策
 *
 * LLMへの入力として危険な文字列パターンを無害化する
 * - システム指示を模倣するパターンを検出・削除
 * - 特殊な区切り文字を無害化
 */
export function sanitizeForPrompt(str: string): string {
  if (!str) return '';

  let sanitized = str;

  // システム指示を模倣するパターンを大文字小文字関係なく検出し削除
  const systemPatterns = [
    /\[SYSTEM\]/gi,
    /\[INST\]/gi,
    /\[\/INST\]/gi,
    /<<SYS>>/gi,
    /<\/SYS>>/gi,
    /```system/gi,
    /```assistant/gi,
    /```user/gi,
  ];

  for (const pattern of systemPatterns) {
    sanitized = sanitized.replace(pattern, '');
  }

  return sanitized.trim();
}

/**
 * キーワード配列のサニタイズ
 *
 * キーワード配列の各要素をサニタイズし、空要素を除去する
 */
export function sanitizeKeywords(keywords: string[]): string[] {
  if (!keywords || !Array.isArray(keywords)) return [];

  return keywords
    .filter((keyword) => typeof keyword === 'string' && keyword.trim() !== '')
    .map((keyword) => sanitizeForPrompt(keyword.trim()))
    .slice(0, 50); // 最大50要素に制限
}

/**
 * 文字列の切り詰め
 *
 * 最大長を超える文字列を切り詰める
 */
export function truncateString(str: string, maxLength: number): string {
  if (!str) return '';
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength);
}

/**
 * 入力バリデーション定数
 */
export const INPUT_LIMITS = {
  ADDITIONAL_CONTEXT_MAX_LENGTH: 10000,
  TOPIC_MAX_LENGTH: 500,
  KEYWORD_MAX_LENGTH: 100,
  KEYWORDS_MAX_COUNT: 50,
} as const;

/**
 * additional_context の検証とサニタイズ
 */
export function validateAndSanitizeAdditionalContext(
  context: string | undefined
): string {
  if (!context) return '';

  let sanitized = sanitizeForPrompt(context);
  sanitized = truncateString(sanitized, INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH);

  return sanitized;
}

/**
 * topic の検証とサニタイズ
 */
export function validateAndSanitizeTopic(topic: string): string {
  if (!topic) return '';

  let sanitized = sanitizeForPrompt(topic);
  sanitized = truncateString(sanitized, INPUT_LIMITS.TOPIC_MAX_LENGTH);

  return sanitized;
}

/**
 * バリデーションエラーの型定義
 */
export interface ValidationError {
  field: string;
  message: string;
}

/**
 * 分析リクエストの検証
 *
 * 各フィールドの長さや形式を検証し、エラーがあれば返す
 */
export function validateAnalysisRequest(body: {
  topic?: string;
  use_case?: string;
  additional_context?: string;
  interest_keywords?: string[];
  tech_keywords?: string[];
  component_keywords?: string[];
  project_keywords?: string[];
}): ValidationError[] {
  const errors: ValidationError[] = [];

  // topic の検証
  if (!body.topic || body.topic.trim() === '') {
    errors.push({ field: 'topic', message: 'トピックは必須です' });
  } else if (body.topic.length > INPUT_LIMITS.TOPIC_MAX_LENGTH) {
    errors.push({
      field: 'topic',
      message: `トピックは${INPUT_LIMITS.TOPIC_MAX_LENGTH}文字以内で入力してください`,
    });
  }

  // use_case の検証
  if (!body.use_case || body.use_case.trim() === '') {
    errors.push({ field: 'use_case', message: 'ユースケースは必須です' });
  }

  // additional_context の検証
  if (
    body.additional_context &&
    body.additional_context.length > INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH
  ) {
    errors.push({
      field: 'additional_context',
      message: `追加コンテキストは${INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH}文字以内で入力してください`,
    });
  }

  // キーワード配列の検証
  const keywordFields = [
    'interest_keywords',
    'tech_keywords',
    'component_keywords',
    'project_keywords',
  ] as const;

  for (const field of keywordFields) {
    const keywords = body[field];
    if (keywords && Array.isArray(keywords)) {
      if (keywords.length > INPUT_LIMITS.KEYWORDS_MAX_COUNT) {
        errors.push({
          field,
          message: `キーワードは${INPUT_LIMITS.KEYWORDS_MAX_COUNT}個以内で選択してください`,
        });
      }
      for (const keyword of keywords) {
        if (
          typeof keyword === 'string' &&
          keyword.length > INPUT_LIMITS.KEYWORD_MAX_LENGTH
        ) {
          errors.push({
            field,
            message: `各キーワードは${INPUT_LIMITS.KEYWORD_MAX_LENGTH}文字以内にしてください`,
          });
          break;
        }
      }
    }
  }

  return errors;
}
