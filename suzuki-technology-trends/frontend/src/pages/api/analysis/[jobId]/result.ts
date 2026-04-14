/**
 * GET /api/analysis/[jobId]/result
 *
 * Get the final result of a completed analysis workflow.
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import { getAnalysisResult, getRunState, getLatestRunStatus } from '../../../../libs/langgraph-client';
import { getInternalTokenFromRequest } from '../../../../libs/auth';

interface AnalysisResultResponse {
  job_id: string;
  expert_team: Array<{ name: string; persona: string }>;
  analysis_results: Record<string, string>;
  final_report: string;
  references: Array<Record<string, unknown>>;
  messages: Array<Record<string, unknown>>;
  created_at: string;
  completed_at: string;
}

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<AnalysisResultResponse | ErrorResponse>
) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', ['GET']);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { jobId } = req.query;
  if (!jobId || typeof jobId !== 'string') {
    return res.status(400).json({ error: 'Bad request', detail: 'jobId is required' });
  }

  // Check authentication
  const token = getInternalTokenFromRequest(req);
  if (!token && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    // First check if the run is completed using run status (more reliable than state.next)
    const runInfo = await getLatestRunStatus(req, jobId);
    const runStatus = runInfo?.status || 'pending';
    const isCompleted = runStatus === 'success';
    if (!isCompleted) {
      return res.status(400).json({
        error: 'Bad request',
        detail: 'Analysis is not yet completed',
      });
    }

    const state = await getRunState(req, jobId);

    // Get the full result
    const result = await getAnalysisResult(req, jobId);

    // Build analysis_results from expert_analyses if available
    const analysisResults: Record<string, string> = {};
    const expertAnalyses = (state.values.expert_analyses as Array<{ expert_name: string; analysis: string }>) || [];
    for (const analysis of expertAnalyses) {
      if (analysis.expert_name && analysis.analysis) {
        analysisResults[analysis.expert_name] = analysis.analysis;
      }
    }

    // Get timestamps from thread metadata
    const createdAt = (state.values.created_at as string) || new Date().toISOString();
    const completedAt = new Date().toISOString();

    return res.status(200).json({
      job_id: jobId,
      expert_team: result.expert_team,
      analysis_results: analysisResults,
      final_report: result.final_report,
      references: result.references,
      messages: result.messages,
      created_at: createdAt,
      completed_at: completedAt,
    });
  } catch (error) {
    console.error('Failed to get result:', error);

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
