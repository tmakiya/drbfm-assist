/**
 * 分析結果表示ページ
 */
import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/router';
import { api } from '@/libs/api';
import {
  getTenantIdFromPath,
  buildDrawerUrl,
  convertDrawingIdsToMarkdownLinks,
  convertDrawingIdsToHtmlLinks,
} from '@/libs/drawingLink';
import { escapeHtml } from '@/libs/sanitize';
import Layout from '@/components/Layout';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface AnalysisProgress {
  job_id: string;
  status: string;
  progress_percentage: number;
  message: string;
  error?: string;
  expert_team?: string[];
  turn?: number;
  expert_name?: string;
}

interface AnalysisResult {
  job_id: string;
  expert_team: Array<{ name: string; persona: string }>;
  analysis_results: { [key: string]: string };
  final_report: string;
  references: Array<any>;
  messages: Array<any>;
  created_at: string;
  completed_at: string;
}

export default function AnalysisResultPage() {
  const router = useRouter();
  const { jobId } = router.query;
  const [progress, setProgress] = useState<AnalysisProgress | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'report' | 'discussion' | 'experts' | 'references'>('report');
  const [tenantId, setTenantId] = useState<string | null>(null);

  // tenant_idをURLパスから取得
  useEffect(() => {
    const id = getTenantIdFromPath();
    setTenantId(id);
  }, []);

  // ポーリング停止判定用のRef（stale closureを回避）
  const resultRef = useRef<AnalysisResult | null>(null);
  const errorRef = useRef<string | null>(null);

  // stateが変わったらrefも更新
  useEffect(() => {
    resultRef.current = result;
  }, [result]);

  useEffect(() => {
    errorRef.current = error;
  }, [error]);

  // 印刷用スタイル
  useEffect(() => {
    const style = document.createElement('style');
    style.innerHTML = `
      @media print {
        body * { visibility: hidden; }
        #printable-area, #printable-area * { visibility: visible; }
        #printable-area { position: absolute; left: 0; top: 0; width: 100%; padding: 20px; }
        .no-print { display: none !important; }
        /* 印刷時は全てのタブコンテンツを表示 */
        #printable-area .hidden { display: block !important; visibility: visible !important; }
        #printable-area > div > div { display: block !important; page-break-inside: avoid; margin-bottom: 30px; }
        .markdown-body { font-size: 11pt; line-height: 1.6; }
        h1 { font-size: 18pt; margin-bottom: 15px; color: #2563eb; }
        h2 { font-size: 14pt; margin-top: 25px; margin-bottom: 10px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
        h3 { font-size: 12pt; margin-top: 15px; margin-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 10pt; }
        th, td { border: 1px solid #d1d5db; padding: 8px; text-align: left; }
        th { background-color: #f3f4f6 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        tr:nth-child(even) { background-color: #f9fafb !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        blockquote { border-left: 4px solid #2563eb; padding-left: 15px; color: #475569; background-color: #f8fafc; }
        /* 専門家カードの印刷スタイル */
        .bg-gradient-to-r { background: #f0f9ff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        /* ページ区切り */
        #report-content, #experts-content, #references-content { page-break-before: auto; }
        .discussion-item, .expert-card { page-break-inside: avoid; }
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  useEffect(() => {
    if (!jobId || typeof jobId !== 'string') return;

    // このページに来た時点でセッションストレージに現在のジョブIDを保存
    sessionStorage.setItem('currentAnalysisJobId', jobId);

    // ポーリング方式で進捗を取得
    const pollProgress = async () => {
      // refを参照してstale closureを回避
      if (resultRef.current || errorRef.current) return;

      try {
        // sessionStorageからrun_idを取得（runs.get()で直接取得するため高速）
        const runId = sessionStorage.getItem(`run_id_${jobId}`);
        const progressData = await api.analysis.getProgress(jobId, runId);
        if (progressData) {
          setProgress(progressData);

          if (progressData.status === 'completed') {
            await fetchResult();
          } else if (progressData.status === 'failed') {
            setError(progressData.error || '分析に失敗しました');
          }
        }
      } catch (error: any) {
        console.error('進捗取得エラー:', error);
        // 401エラーの場合はログイン画面にリダイレクトされる（api.tsのインターセプターで処理）
        // 404の場合は結果を取得してみる（既に完了している可能性）
        if (error.response?.status === 404) {
          await fetchResult();
        }
        // その他のエラーは無視してポーリングを継続
      }
    };

    // 初回実行
    pollProgress();

    // 定期的にポーリング（5秒間隔に変更してレート制限を回避）
    const interval = setInterval(() => {
      // refを参照してstale closureを回避
      if (resultRef.current || errorRef.current) {
        clearInterval(interval);
        return;
      }
      pollProgress();
    }, 5000);

    return () => {
      clearInterval(interval);
      // ページを離れる際にセッションストレージをクリア
      sessionStorage.removeItem('currentAnalysisJobId');
    };
  }, [jobId]); // resultとerrorを依存配列から除外

  const fetchResult = async () => {
    if (!jobId || typeof jobId !== 'string') return;
    try {
      const resultData = await api.analysis.getResult(jobId);
      setResult(resultData);
      setProgress(null); // 進捗表示を終了
    } catch (error: any) {
      console.error('結果取得エラー:', error);
      // 401エラーの場合はログイン画面にリダイレクトされる（api.tsのインターセプターで処理）
      // その他のエラーのみエラーメッセージを表示
      if (error.response?.status !== 401) {
        setError('結果の取得に失敗しました');
      }
    }
  };

  const handleDownloadHTML = () => {
    if (!result) return;

    // 専門家プロフィールのHTMLを生成（XSSエスケープ適用）
    const expertsHtml = result.expert_team && result.expert_team.length > 0
      ? `
        <h2>🎓 召集された専門家チーム</h2>
        <div class="experts-grid">
          ${result.expert_team.map((expert, idx) => `
            <div class="expert-card">
              <h3>${escapeHtml(expert.name)}</h3>
              <p>${convertDrawingIdsToHtmlLinks(escapeHtml(expert.persona), tenantId)}</p>
            </div>
          `).join('')}
        </div>
      `
      : '';

    // 議論ログのHTMLを生成（XSSエスケープ適用）
    const discussionHtml = result.messages && result.messages.length > 0
      ? `
        <h2>💬 議論ログ</h2>
        <div class="discussion-log">
          ${result.messages.map((msg, idx) => `
            <div class="discussion-item">
              <div class="discussion-header">
                <strong>${escapeHtml(msg.agent_type)}</strong> - ターン ${msg.turn}
              </div>
              <div class="discussion-content">${convertDrawingIdsToHtmlLinks(escapeHtml(msg.content), tenantId)}</div>
            </div>
          `).join('')}
        </div>
      `
      : '';

    // 参照情報源のHTMLを生成（XSSエスケープ適用）
    const referencesHtml = result.references && result.references.length > 0
      ? `
        <h2>📚 参照情報源</h2>
        <table>
          <thead>
            <tr>
              <th>No.</th>
              <th>図面ID</th>
              <th>プロジェクト</th>
            </tr>
          </thead>
          <tbody>
            ${result.references.map((ref, idx) => `
              <tr>
                <td>${idx + 1}</td>
                <td>${ref.drawing_id && tenantId
                  ? `<a href="${buildDrawerUrl(ref.drawing_id, tenantId)}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: underline;">${escapeHtml(ref.drawing_id)}</a>`
                  : escapeHtml(ref.drawing_id || '-')
                }</td>
                <td>${escapeHtml(ref.project || '-')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `
      : '';
    
    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="UTF-8">
        <title>CADDi Drawer 技術分析レポート</title>
        <style>
          body { font-family: 'Hiragino Sans', 'Meiryo', sans-serif; line-height: 1.8; padding: 40px; max-width: 900px; margin: 0 auto; color: #333; }
          h1 { color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 15px; margin-bottom: 30px; }
          h2 { color: #1e40af; margin-top: 40px; padding-bottom: 10px; border-bottom: 2px solid #e5e7eb; }
          h3 { color: #374151; margin-top: 25px; }
          table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }
          th, td { border: 1px solid #d1d5db; padding: 12px; text-align: left; }
          th { background-color: #f3f4f6; font-weight: 600; }
          tr:nth-child(even) { background-color: #f9fafb; }
          code { background-color: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
          blockquote { border-left: 4px solid #2563eb; margin: 20px 0; padding: 15px 20px; background-color: #f8fafc; color: #475569; }
          .metadata { margin-bottom: 30px; padding: 20px; background-color: #f0f9ff; border-radius: 8px; border: 1px solid #bae6fd; }
          .experts-grid { display: grid; gap: 20px; margin: 20px 0; }
          .expert-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; }
          .expert-card h3 { color: #2563eb; margin-top: 0; margin-bottom: 10px; }
          .expert-card p { color: #64748b; margin: 0; font-size: 14px; }
          .discussion-log { margin: 20px 0; }
          .discussion-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 15px; }
          .discussion-header { color: #2563eb; font-weight: 600; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #e2e8f0; }
          .discussion-content { color: #475569; white-space: pre-wrap; }
          hr { border: none; border-top: 2px solid #e5e7eb; margin: 40px 0; }
          ul, ol { padding-left: 25px; }
          li { margin-bottom: 8px; }
          @media print {
            body { padding: 20px; }
            .expert-card, .discussion-item { break-inside: avoid; }
          }
        </style>
      </head>
      <body>
        <h1>🚗 CADDi Drawer 技術分析 最終報告書</h1>
        <div class="metadata">
          <p><strong>📋 ジョブID:</strong> ${escapeHtml(result.job_id)}</p>
          <p><strong>📅 作成日:</strong> ${escapeHtml(new Date(result.created_at).toLocaleString('ja-JP'))}</p>
          <p><strong>✅ 完了日:</strong> ${result.completed_at ? escapeHtml(new Date(result.completed_at).toLocaleString('ja-JP')) : '-'}</p>
        </div>
        
        ${expertsHtml}
        
        <hr>
        
        <h2>📄 最終レポート</h2>
        <div class="content">
          ${document.getElementById('report-content')?.innerHTML || ''}
        </div>
        
        <hr>
        
        ${discussionHtml}
        
        <hr>
        
        ${referencesHtml}
        
        <hr>
        <p style="text-align: center; color: #9ca3af; font-size: 12px;">
          Generated by CADDi Drawer AI Technology Review System
        </p>
      </body>
      </html>
    `;
    
    const blob = new Blob([htmlContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `CADDi_Drawer_Report_${new Date().toISOString().slice(0,10)}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    window.print();
  };

  if (error) {
    return (
      <Layout>
        <div className="container mx-auto px-4 py-8">
          <div className="bg-red-50 border-l-4 border-red-500 p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            </div>
          </div>
          <button
            onClick={() => router.push('/analysis/new')}
            className="mt-4 inline-flex items-center bg-caddi-blue text-white py-2 px-4 rounded hover:bg-caddi-blue-dark"
          >
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            戻る
          </button>
        </div>
      </Layout>
    );
  }

  if (!result) {
    return (
      <Layout>
        <div className="container mx-auto px-4 py-16 flex flex-col items-center justify-center">
          <div className="w-full max-w-lg">
            <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">AI専門家チームが分析中...</h2>
            
            <div className="mb-8">
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-caddi-blue-dark">
                  {progress?.message || '分析を開始しています...'}
                </span>
                <span className="text-sm font-medium text-caddi-blue-dark">
                  {Math.round(progress?.progress_percentage || 0)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div 
                  className="bg-caddi-blue h-2.5 rounded-full transition-all duration-500 ease-out" 
                  style={{ width: `${progress?.progress_percentage || 0}%` }}
                ></div>
              </div>
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-lg border border-gray-200">
              <div className="px-4 py-5 sm:px-6 bg-gray-50">
                <h3 className="text-lg leading-6 font-medium text-gray-900">
                  現在のステータス
                </h3>
              </div>
              <div className="border-t border-gray-200 px-4 py-5 sm:p-0">
                <dl className="sm:divide-y sm:divide-gray-200">
                  <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                    <dt className="text-sm font-medium text-gray-500">フェーズ</dt>
                    <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                      {progress?.turn ? `ターン ${progress.turn} / 2` : '準備中'}
                    </dd>
                  </div>
                  {progress?.expert_name && (
                    <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                      <dt className="text-sm font-medium text-gray-500">担当エージェント</dt>
                      <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 flex items-center">
                        <span className="h-2 w-2 bg-green-400 rounded-full mr-2 animate-pulse"></span>
                        {progress.expert_name}
                      </dd>
                    </div>
                  )}
                  {progress?.expert_team && (
                    <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
                      <dt className="text-sm font-medium text-gray-500">専門家チーム</dt>
                      <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                        <ul className="list-disc list-inside">
                          {progress.expert_team.map((expert, idx) => (
                            <li key={idx}>{expert}</li>
                          ))}
                        </ul>
                      </dd>
                    </div>
                  )}
                </dl>
              </div>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8 no-print">
          <h1 className="text-3xl font-bold text-gray-900">分析完了</h1>
          <div className="flex gap-3">
            <button
              onClick={handlePrint}
              className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              <svg className="-ml-1 mr-2 h-5 w-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
              </svg>
              PDFダウンロード (印刷)
            </button>
            <button
              onClick={handleDownloadHTML}
              className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              <svg className="-ml-1 mr-2 h-5 w-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              HTMLダウンロード
            </button>
            <button
              onClick={() => router.push('/analysis/new')}
              className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-caddi-blue hover:bg-caddi-blue-dark"
            >
              <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              戻る
            </button>
          </div>
        </div>

        <div className="bg-white shadow rounded-lg overflow-hidden border border-gray-200" id="printable-area">
          <div className="border-b border-gray-200 no-print">
            <nav className="-mb-px flex">
              <button
                onClick={() => setActiveTab('report')}
                className={`${
                  activeTab === 'report'
                    ? 'border-caddi-blue text-caddi-blue'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-6 border-b-2 font-medium text-sm flex-1 text-center`}
              >
                📄 最終レポート
              </button>
              <button
                onClick={() => setActiveTab('discussion')}
                className={`${
                  activeTab === 'discussion'
                    ? 'border-caddi-blue text-caddi-blue'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-6 border-b-2 font-medium text-sm flex-1 text-center`}
              >
                💬 議論ログ
              </button>
              <button
                onClick={() => setActiveTab('experts')}
                className={`${
                  activeTab === 'experts'
                    ? 'border-caddi-blue text-caddi-blue'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-6 border-b-2 font-medium text-sm flex-1 text-center`}
              >
                🎓 召集された専門家
              </button>
              <button
                onClick={() => setActiveTab('references')}
                className={`${
                  activeTab === 'references'
                    ? 'border-caddi-blue text-caddi-blue'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-6 border-b-2 font-medium text-sm flex-1 text-center`}
              >
                📚 参照情報源
              </button>
            </nav>
          </div>

          <div className="p-8">
            {/* 最終レポート */}
            <div className={activeTab === 'report' ? 'block' : 'hidden'}>
              <div className="prose max-w-none markdown-body" id="report-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({node, ...props}) => (
                      <div className="overflow-x-auto my-6">
                        <table className="min-w-full divide-y divide-gray-300 border border-gray-200 text-sm" {...props} />
                      </div>
                    ),
                    thead: ({node, ...props}) => <thead className="bg-gray-100" {...props} />,
                    tbody: ({node, ...props}) => <tbody className="bg-white divide-y divide-gray-200" {...props} />,
                    tr: ({node, ...props}) => <tr className="hover:bg-gray-50" {...props} />,
                    th: ({node, ...props}) => <th className="px-4 py-3 text-left text-xs font-bold text-gray-700 uppercase tracking-wider border border-gray-200 bg-gray-100" {...props} />,
                    td: ({node, ...props}) => <td className="px-4 py-3 whitespace-normal text-sm text-gray-700 border border-gray-200" {...props} />,
                    h1: ({node, ...props}) => <h1 className="text-2xl font-bold text-gray-900 mt-8 mb-4 pb-2 border-b" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-xl font-semibold text-gray-800 mt-6 mb-3" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-lg font-medium text-gray-800 mt-4 mb-2" {...props} />,
                    ul: ({node, ...props}) => <ul className="list-disc list-inside my-4 pl-4" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal list-inside my-4 pl-4" {...props} />,
                    li: ({node, ...props}) => <li className="mb-1" {...props} />,
                    blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-600 my-4" {...props} />,
                    p: ({node, ...props}) => <p className="my-3 leading-relaxed" {...props} />,
                    a: ({node, href, children, ...props}) => (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-caddi-blue hover:underline"
                        {...props}
                      >
                        {children}
                      </a>
                    ),
                  }}
                >
                  {convertDrawingIdsToMarkdownLinks(result.final_report, tenantId)}
                </ReactMarkdown>
              </div>
            </div>

            {/* 議論ログ */}
            <div className={activeTab === 'discussion' ? 'block' : 'hidden'}>
              <div className="space-y-6">
                {result.messages.map((msg, idx) => (
                  <div key={idx} className="bg-gray-50 rounded-lg p-6 border border-gray-200">
                    <div className="flex items-center mb-4">
                      <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center text-caddi-blue font-bold mr-3">
                        {msg.agent_type === 'Summarizer' ? 'S' : msg.agent_type.charAt(0)}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-gray-900">{msg.agent_type}</div>
                        <div className="text-xs text-gray-500">ターン {msg.turn}</div>
                      </div>
                    </div>
                    <div className="prose max-w-none text-sm text-gray-700">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 召集された専門家 */}
            <div className={activeTab === 'experts' ? 'block' : 'hidden'} id="experts-content">
              <div className="mb-6">
                <h2 className="text-xl font-semibold text-gray-900 mb-2">オーケストレーションで召集された専門家チーム</h2>
                <p className="text-gray-600">
                  分析トピックと選択されたテーマに基づき、AIオーケストレーターが最適な専門家チームを選定しました。
                </p>
              </div>
              
              {result.expert_team && result.expert_team.length > 0 ? (
                <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-1">
                  {result.expert_team.map((expert, idx) => (
                    <div key={idx} className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl overflow-hidden shadow-sm">
                      <div className="px-6 py-4 bg-gradient-to-r from-caddi-blue to-blue-700">
                        <div className="flex items-center">
                          <div className="h-12 w-12 rounded-full bg-white flex items-center justify-center text-caddi-blue font-bold text-xl shadow-md mr-4">
                            {expert.name.charAt(0)}
                          </div>
                          <div>
                            <h3 className="text-xl font-bold text-white">{expert.name}</h3>
                            <p className="text-blue-100 text-sm">専門家エージェント #{idx + 1}</p>
                          </div>
                        </div>
                      </div>
                      <div className="p-6">
                        <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
                          プロフィール・専門領域
                        </h4>
                        <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                          {expert.persona}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 bg-gray-50 rounded-lg">
                  専門家チームの情報がありません。
                </div>
              )}
            </div>

            {/* 参照情報源 */}
            <div className={activeTab === 'references' ? 'block' : 'hidden'} id="references-content">
              {result.references && result.references.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 border border-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">No.</th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">図面ID</th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">プロジェクト</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {result.references.map((ref, idx) => (
                        <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{idx + 1}</td>
                          <td className="px-6 py-4 text-sm text-gray-500">
                            {ref.drawing_id && tenantId ? (
                              <a
                                href={buildDrawerUrl(ref.drawing_id, tenantId) || '#'}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-caddi-blue hover:underline"
                              >
                                {ref.drawing_id}
                              </a>
                            ) : (
                              ref.drawing_id || '-'
                            )}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500">{ref.project || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  参照情報源はありません。
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}