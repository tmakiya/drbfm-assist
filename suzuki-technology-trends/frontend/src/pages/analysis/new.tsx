/**
 * 新規分析作成ページ
 *
 * LangGraph Platform + ISP を使用した分析ワークフロー
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/router';
import { api } from '@/libs/api';
import { INPUT_LIMITS } from '@/libs/sanitize';
import Layout from '@/components/Layout';

export default function NewAnalysis() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    topic: '自動車業界の最新技術トレンド',
    use_case: '技術探索/経営',
    interest_keywords: [] as string[],
    tech_keywords: [] as string[],
    component_keywords: [] as string[],
    project_keywords: [] as string[],
    additional_context: 'スズキの小型車戦略と新興国市場を考慮した分析を実施してください。',
  });

  const [loading, setLoading] = useState(false);
  const [filterOptions, setFilterOptions] = useState<{ [key: string]: { key: string; doc_count: number }[] }>({});
  const [ragStatus, setRagStatus] = useState<any>(null);
  const [ragError, setRagError] = useState<string | null>(null);
  const [checkingRag, setCheckingRag] = useState(true);
  const [filteredDocCount, setFilteredDocCount] = useState<number | null>(null);
  const [loadingFilterPreview, setLoadingFilterPreview] = useState(false);

  // Debounce timer ref for filter preview
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // ページ初期化時に状態をリセット（分析中断後の再開対応）
  useEffect(() => {
    // 前回の分析セッションがあればクリア
    sessionStorage.removeItem('currentAnalysisJobId');

    // フォームデータを初期状態にリセット
    setFormData({
      topic: '自動車業界の最新技術トレンド',
      use_case: '技術探索/経営',
      interest_keywords: [],
      tech_keywords: [],
      component_keywords: [],
      project_keywords: [],
      additional_context: 'スズキの小型車戦略と新興国市場を考慮した分析を実施してください。',
    });
    setLoading(false);
    setFilteredDocCount(null);

    console.log('新規分析ページ: 状態をリセットしました');
  }, []);

  // RAG状態とフィルターオプションを初期確認
  useEffect(() => {
    const checkRagAndFilters = async () => {
      try {
        setCheckingRag(true);
        setRagError(null);
        const status = await api.rag.getStatus();
        setRagStatus(status);

        // エラー状態をチェック
        if (status.status === 'error') {
          setRagError(status.error || 'ISPへの接続に失敗しました');
          console.error('RAGエラー:', status.error, 'index_alias:', status.index_alias);
          return;
        }

        // フィルターオプションを取得（件数付き）
        if (status.indexed_documents > 0) {
          const filters = await api.filters.get();
          // ISPからのレスポンス形式を変換（件数付き）
          setFilterOptions({
            '課題テーマ': filters.issues || [],
            '技術テーマ': filters.technologies || [],
            '構成品テーマ': filters.components || [],
            'プロジェクト名': filters.projects || [],
          });
          console.log(`RAGデータ: ${status.indexed_documents}件`);
        }
      } catch (error) {
        console.error('RAG状態確認エラー:', error);
        setRagError(error instanceof Error ? error.message : 'RAG状態の確認に失敗しました');
      } finally {
        setCheckingRag(false);
      }
    };

    checkRagAndFilters();
  }, []);

  const handleStartAnalysis = async () => {
    if (!formData.topic.trim()) {
      alert('分析トピックを入力してください');
      return;
    }

    // 既に分析中の場合は処理を中断
    if (loading) {
      console.log('既に分析を開始しています');
      return;
    }

    setLoading(true);
    try {
      const requestData = {
        topic: formData.topic.trim(),
        use_case: formData.use_case,
        interest_keywords: formData.interest_keywords,
        tech_keywords: formData.tech_keywords,
        component_keywords: formData.component_keywords,
        project_keywords: formData.project_keywords,
        additional_context: formData.additional_context,
      };
      
      const response = await api.analysis.start(requestData);

      // 分析開始成功時にジョブIDをセッションストレージに保存
      sessionStorage.setItem('currentAnalysisJobId', response.job_id);
      // run_idをsessionStorageに保存（ポーリング時にruns.get()で直接取得するため）
      if (response.run_id) {
        sessionStorage.setItem(`run_id_${response.job_id}`, response.run_id);
      }

      router.push(`/analysis/${response.job_id}`);
    } catch (error: any) {
      console.error('分析開始エラー:', error);
      const errorMessage = error.response?.data?.detail || '分析の開始に失敗しました';
      alert(`エラー: ${errorMessage}`);
      setLoading(false);
    }
    // 成功時はページ遷移するのでsetLoading(false)は不要
  };

  const toggleKeyword = (field: keyof typeof formData, value: string) => {
    setFormData(prev => {
      const current = prev[field] as string[];
      const newFormData = current.includes(value)
        ? { ...prev, [field]: current.filter(item => item !== value) }
        : { ...prev, [field]: [...current, value] };
      
      // フィルター変更時にプレビューを更新
      updateFilterPreview(newFormData);
      
      return newFormData;
    });
  };

  // Actual filter preview fetch logic
  const fetchFilterPreview = useCallback(async (data: typeof formData) => {
    if (!ragStatus || ragStatus.indexed_documents === 0) {
      return;
    }

    try {
      setLoadingFilterPreview(true);
      const preview = await api.rag.previewFilter({
        interest_keywords: data.interest_keywords,
        tech_keywords: data.tech_keywords,
        component_keywords: data.component_keywords,
        project_keywords: data.project_keywords,
      });
      setFilteredDocCount(preview.filtered_count);
    } catch (error) {
      console.error('フィルタープレビューエラー:', error);
      setFilteredDocCount(null);
    } finally {
      setLoadingFilterPreview(false);
    }
  }, [ragStatus]);

  // Debounced filter preview update (300ms)
  const updateFilterPreview = useCallback((data: typeof formData) => {
    // Cancel any pending debounce timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Check if any filters are applied
    const hasFilters =
      data.interest_keywords.length > 0 ||
      data.tech_keywords.length > 0 ||
      data.component_keywords.length > 0 ||
      data.project_keywords.length > 0;

    if (!hasFilters) {
      setFilteredDocCount(null);
      return;
    }

    // Debounce the API call
    debounceTimerRef.current = setTimeout(() => {
      fetchFilterPreview(data);
    }, 300);
  }, [fetchFilterPreview]);

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const renderMultiSelect = (label: string, field: keyof typeof formData, options: { key: string; doc_count: number }[]) => {
    if (!options || options.length === 0) {
      return null;
    }

    return (
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">{label}</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {options.map((option) => {
            const isSelected = (formData[field] as string[]).includes(option.key);

            return (
              <label
                key={option.key}
                className={`relative flex items-center p-3 rounded-lg border transition-all ${
                  isSelected
                    ? 'bg-blue-50 border-caddi-blue cursor-pointer'
                    : 'bg-white border-gray-300 hover:border-caddi-blue/50 cursor-pointer'
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={isSelected}
                  onChange={() => {
                    toggleKeyword(field, option.key);
                  }}
                />
                <span
                  className={`text-sm ${
                    isSelected
                      ? 'text-caddi-blue-dark font-medium'
                      : 'text-gray-700'
                  }`}
                >
                  {option.key}
                  <span className="ml-1 text-xs text-gray-400">
                    ({option.doc_count}件)
                  </span>
                </span>
                {isSelected && (
                  <svg
                    className="absolute right-3 top-3 h-5 w-5 text-caddi-blue"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </label>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Layout>
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          {/* ヘッダー */}
          <div className="text-center mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">新しい分析を開始</h1>
            <p className="text-gray-600">CADDi Drawer 技術レビューシステム</p>
          </div>

          {checkingRag ? (
            <div className="bg-white rounded-2xl shadow-xl p-12 text-center">
              <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-caddi-blue mx-auto mb-4"></div>
              <p className="text-gray-600 text-lg">RAG状態を確認中...</p>
            </div>
          ) : (
            <>
              {/* 分析設定 */}
              <div className="bg-white shadow-xl rounded-2xl p-8">
                <h2 className="text-2xl font-semibold text-gray-900 mb-6">分析条件の設定</h2>

                  <div className="space-y-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">分析トピック</label>
                      <div className="w-full px-4 py-2 bg-gray-100 border border-gray-300 rounded-lg text-gray-700">
                        {formData.topic}
                      </div>
                      <p className="mt-1 text-xs text-gray-500">※ 分析トピックは固定されています</p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">ユースケース</label>
                      <select
                        value={formData.use_case}
                        onChange={(e) => setFormData({ ...formData, use_case: e.target.value })}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-caddi-blue focus:border-transparent"
                      >
                        <option value="技術探索/経営">📊 技術探索/経営（経営層向け）</option>
                        <option value="部品開発アシスト/設計">🔧 部品開発アシスト/設計（設計者向け）</option>
                      </select>
                      <p className="mt-2 text-sm text-gray-500">
                        {formData.use_case === '技術探索/経営' || formData.use_case === '最新技術トレンド調査'
                          ? '技術の具体的な内容、スズキの戦略・強みへのフィット、開発推進体制の提案を含む経営層向けレポートを生成します。' 
                          : '技術提案と効果予測、メリット・デメリットの比較、考慮すべきポイントを含む設計者向けレポートを生成します。'}
                      </p>
                    </div>

                <div className="border-t border-gray-200 pt-6">
                <div className="flex items-center justify-between mb-2">
                    <h3 className="text-lg font-medium text-gray-900">データの絞り込み（フィルター）</h3>
                    <button
                      onClick={() => {
                        setFormData(prev => ({
                          ...prev,
                          interest_keywords: [],
                          tech_keywords: [],
                          component_keywords: [],
                          project_keywords: [],
                        }));
                        setFilteredDocCount(null);
                      }}
                      disabled={!(formData.interest_keywords.length > 0 ||
                        formData.tech_keywords.length > 0 ||
                        formData.component_keywords.length > 0 ||
                        formData.project_keywords.length > 0)}
                      className={`flex items-center px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                        formData.interest_keywords.length > 0 ||
                        formData.tech_keywords.length > 0 ||
                        formData.component_keywords.length > 0 ||
                        formData.project_keywords.length > 0
                          ? 'text-red-600 bg-red-50 border border-red-200 hover:bg-red-100 hover:border-red-300'
                          : 'text-gray-300 bg-gray-50 border border-gray-200 cursor-not-allowed'
                      }`}
                    >
                      <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      フィルタを外す
                    </button>
                  </div>
                  <p className="text-sm text-gray-500 mb-4">アップロードされたファイルから抽出されたキーワードで分析対象を絞り込めます。</p>
                  
                  {ragStatus && ragStatus.indexed_documents > 0 && (
                    <div className="mb-4 p-4 bg-gradient-to-r from-blue-50 to-blue-50 border border-caddi-blue/20 rounded-lg">
                      <p className="text-sm font-medium text-caddi-blue-dark">
                        📊 解析対象：
                        <strong className="text-lg">
                          {filteredDocCount !== null ? filteredDocCount : ragStatus.indexed_documents}
                        </strong>
                        {' / '}
                        <span>{ragStatus.indexed_documents}</span> 件
                        {loadingFilterPreview && (
                          <span className="ml-2 text-xs text-gray-500 italic">計算中...</span>
                        )}
                        {filteredDocCount === 0 && (
                          <span className="ml-2 text-sm text-red-600">（条件が厳しすぎます）</span>
                        )}
                      </p>
                    </div>
                  )}
                  
                  {renderMultiSelect("課題テーマ", "interest_keywords", filterOptions['課題テーマ'] || [])}
                  {renderMultiSelect("技術テーマ", "tech_keywords", filterOptions['技術テーマ'] || [])}
                  {renderMultiSelect("構成品テーマ", "component_keywords", filterOptions['構成品テーマ'] || [])}
                </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">追加コンテキスト</label>
                      <textarea
                        value={formData.additional_context}
                        onChange={(e) => setFormData({ ...formData, additional_context: e.target.value })}
                        rows={4}
                        maxLength={INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH}
                        className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-caddi-blue focus:border-transparent ${
                          formData.additional_context.length > INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH * 0.9
                            ? 'border-yellow-500 bg-yellow-50'
                            : 'border-gray-300'
                        }`}
                        placeholder="分析における前提条件や特に注目してほしいポイントなどを自由に入力してください。"
                      />
                      <div className="mt-1 flex justify-between items-center">
                        <p className="text-xs text-gray-500">最大{INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH.toLocaleString()}文字</p>
                        <p className={`text-xs ${
                          formData.additional_context.length > INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH * 0.9
                            ? 'text-yellow-600 font-medium'
                            : 'text-gray-500'
                        }`}>
                          {formData.additional_context.length.toLocaleString()} / {INPUT_LIMITS.ADDITIONAL_CONTEXT_MAX_LENGTH.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end">
                    <button
                      onClick={handleStartAnalysis}
                      className={`px-8 py-3 text-white font-semibold rounded-lg transition-colors shadow-md hover:shadow-lg 
                        ${!formData.topic.trim() || loading ? 'bg-gray-300 cursor-not-allowed' : 'bg-caddi-blue hover:bg-caddi-blue-dark'}`}
                      disabled={!formData.topic.trim() || loading}
                    >
                      {loading ? (
                        <>
                          <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                          分析を開始中...
                        </>
                      ) : '分析を開始'}
                    </button>
                  </div>
                </div>
            </>
          )}
        </div>
      </div>
    </Layout>
  );
}
