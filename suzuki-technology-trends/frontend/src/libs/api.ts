/**
 * APIクライアント: Next.js API Routes経由でLangGraph Platformと通信
 *
 * 認証: internal tokenはリクエストヘッダーで自動的に転送される
 */
import axios from 'axios';

// Next.js API Routes（サーバーサイド）を使用
const API_PREFIX = `${process.env.NEXT_PUBLIC_BASE_PATH || ''}/api`;

// Axiosインスタンスの作成
const apiClient = axios.create({
  headers: {
    'Content-Type': 'application/json',
  },
});

// APIエンドポイント
export const api = {
  // フィルタ
  filters: {
    get: async () => {
      const response = await apiClient.get(`${API_PREFIX}/filters`);
      return response.data;
    },
  },

  // RAG管理
  rag: {
    getStatus: async () => {
      const response = await apiClient.get(`${API_PREFIX}/rag/status`);
      return response.data;
    },
    previewFilter: async (filters: {
      interest_keywords: string[];
      tech_keywords: string[];
      component_keywords: string[];
      project_keywords: string[];
    }) => {
      const response = await apiClient.post(`${API_PREFIX}/rag/preview`, filters);
      return response.data;
    },
  },

  // 分析
  analysis: {
    start: async (request: {
      topic: string;
      use_case: string;
      interest_keywords: string[];
      tech_keywords: string[];
      component_keywords: string[];
      project_keywords: string[];
      additional_context?: string;
    }) => {
      const response = await apiClient.post(`${API_PREFIX}/analysis/start`, request);
      return response.data;
    },
    getProgress: async (jobId: string, runId?: string | null) => {
      const params = runId ? `?runId=${runId}` : '';
      const response = await apiClient.get(`${API_PREFIX}/analysis/${jobId}/progress${params}`);
      return response.data;
    },
    getResult: async (jobId: string) => {
      const response = await apiClient.get(`${API_PREFIX}/analysis/${jobId}/result`);
      return response.data;
    },
  },
};

export default apiClient;
