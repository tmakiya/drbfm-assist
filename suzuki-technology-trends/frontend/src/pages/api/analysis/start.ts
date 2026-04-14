/**
 * POST /api/analysis/start
 *
 * Start a new analysis workflow via LangGraph Platform.
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import { startAnalysis, AnalysisInput } from '../../../libs/langgraph-client';
import { getInternalTokenFromRequest } from '../../../libs/auth';
import {
  validateAnalysisRequest,
  validateAndSanitizeTopic,
  validateAndSanitizeAdditionalContext,
  sanitizeKeywords,
} from '../../../libs/sanitize';

interface StartAnalysisRequest {
  topic: string;
  use_case: string;
  interest_keywords: string[];
  tech_keywords: string[];
  component_keywords: string[];
  project_keywords: string[];
  additional_context?: string;
}

interface StartAnalysisResponse {
  job_id: string;
  thread_id: string;
  run_id: string;
  status: string;
}

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<StartAnalysisResponse | ErrorResponse>
) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', ['POST']);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Check authentication
  const token = getInternalTokenFromRequest(req);
  if (!token && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const body = req.body as StartAnalysisRequest;

    // Validate input fields (length, format, etc.)
    const validationErrors = validateAnalysisRequest(body);
    if (validationErrors.length > 0) {
      return res.status(400).json({
        error: 'Validation error',
        detail: validationErrors.map((e) => `${e.field}: ${e.message}`).join(', '),
      });
    }

    // Sanitize all inputs to prevent prompt injection
    const input: AnalysisInput = {
      topic: validateAndSanitizeTopic(body.topic),
      use_case: body.use_case.trim(),
      interest_keywords: sanitizeKeywords(body.interest_keywords || []),
      tech_keywords: sanitizeKeywords(body.tech_keywords || []),
      component_keywords: sanitizeKeywords(body.component_keywords || []),
      project_keywords: sanitizeKeywords(body.project_keywords || []),
      additional_context: validateAndSanitizeAdditionalContext(body.additional_context),
    };

    const { threadId, runId } = await startAnalysis(req, input);

    // Return both thread_id and run_id for proper LangGraph tracking
    return res.status(200).json({
      job_id: threadId,
      thread_id: threadId,
      run_id: runId,
      status: 'running',
    });
  } catch (error) {
    console.error('Failed to start analysis:', error);
    return res.status(500).json({
      error: 'Internal server error',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
