/**
 * GET /api/analysis/[jobId]/progress
 *
 * Get the current progress of an analysis workflow.
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import { getRunState, getLatestRunStatus, getRunStatus } from '../../../../libs/langgraph-client';
import { getInternalTokenFromRequest } from '../../../../libs/auth';

interface ProgressResponse {
  job_id: string;
  status: string;
  progress_percentage: number;
  message: string;
  expert_team?: string[];
  turn?: number;
  expert_name?: string;
  error?: string;
}

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<ProgressResponse | ErrorResponse>
) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', ['GET']);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { jobId, runId } = req.query;
  if (!jobId || typeof jobId !== 'string') {
    return res.status(400).json({ error: 'Bad request', detail: 'jobId is required' });
  }

  // Check authentication
  const token = getInternalTokenFromRequest(req);
  if (!token && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    // runのステータスを確認（state.nextよりも信頼性が高い）
    // runIdが指定されている場合はruns.get()で直接取得（高速）
    // なければフォールバックでruns.list()を使用
    let runStatus: string = 'pending';
    if (runId && typeof runId === 'string') {
      const runInfo = await getRunStatus(req, jobId, runId);
      runStatus = runInfo?.status || 'pending';
    } else {
      const runInfo = await getLatestRunStatus(req, jobId);
      runStatus = runInfo?.status || 'pending';
    }

    // runステータスで判定
    const isCompleted = runStatus === 'success';
    const isFailed = runStatus === 'error' || runStatus === 'timeout' || runStatus === 'interrupted';

    // pending状態の場合は早期リターン（stateの取得をスキップしてタイムアウトを回避）
    if (runStatus === 'pending') {
      return res.status(200).json({
        job_id: jobId,
        status: 'running',
        progress_percentage: 0,
        message: '分析を開始しています...',
      });
    }

    const state = await getRunState(req, jobId);
    const values = state.values;

    // 現在のノードを判定（state.nextの最初の要素）
    const currentNode = state.next[0] as string | undefined;

    // ノード名からプログレスを計算
    const nodeProgressMap: Record<string, { progress: number; message: string; turn?: number }> = {
      'select_expert_team': { progress: 10, message: '専門家チームを選定中...' },
      'turn1_analysis': { progress: 30, message: 'ターン1: 分析視点の整理中...', turn: 1 },
      'search_rag': { progress: 50, message: 'RAG検索を実行中...' },
      'turn2_analysis': { progress: 70, message: 'ターン2: 詳細分析中...', turn: 2 },
      'generate_report': { progress: 90, message: '最終レポートを生成中...' },
    };

    let progressPercentage = 0;
    let message = 'Processing...';
    let turn: number | undefined;
    let expertName: string | undefined;

    const expertTeam = values.expert_team as Array<{ name: string }> | undefined;
    const errorMessage = values.error as string | undefined;

    if (isFailed) {
      progressPercentage = 0;
      message = errorMessage ? `エラー: ${errorMessage}` : '分析に失敗しました';
    } else if (isCompleted) {
      progressPercentage = 100;
      message = '分析が完了しました';
    } else if (currentNode && nodeProgressMap[currentNode]) {
      const nodeInfo = nodeProgressMap[currentNode];
      progressPercentage = nodeInfo.progress;
      message = nodeInfo.message;
      turn = nodeInfo.turn;
    }

    return res.status(200).json({
      job_id: jobId,
      status: isFailed ? 'failed' : (isCompleted ? 'completed' : 'running'),
      progress_percentage: progressPercentage,
      message,
      expert_team: expertTeam?.map((e) => e.name),
      turn,
      expert_name: expertName,
      error: errorMessage,
    });
  } catch (error) {
    console.error('Failed to get progress:', error);

    // If thread not found, return completed (might have been cleaned up)
    if (error instanceof Error && error.message.includes('not found')) {
      return res.status(404).json({
        error: 'Not found',
        detail: 'Analysis job not found',
      });
    }

    return res.status(500).json({
      error: 'Internal server error',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
