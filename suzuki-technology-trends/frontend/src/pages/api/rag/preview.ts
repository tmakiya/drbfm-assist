/**
 * POST /api/rag/preview
 *
 * Get document count with applied filters (preview).
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import {
  getFilteredDocumentCount,
  getFilterOptionsWithCounts,
  FilterCriteria,
  FilterOptionsWithCounts,
} from '../../../libs/isp-client';
import { getInternalTokenFromRequest } from '../../../libs/auth';

interface PreviewRequest {
  interest_keywords?: string[];
  tech_keywords?: string[];
  component_keywords?: string[];
  project_keywords?: string[];
}

interface PreviewResponse {
  filtered_count: number;
  total_count: number;
  available_options: FilterOptionsWithCounts;
}

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<PreviewResponse | ErrorResponse>
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
    const body = req.body as PreviewRequest;

    const filters: FilterCriteria = {
      interest_keywords: body.interest_keywords,
      tech_keywords: body.tech_keywords,
      component_keywords: body.component_keywords,
      project_keywords: body.project_keywords,
    };

    // Fetch document count and available options in parallel
    const [countResult, availableOptions] = await Promise.all([
      getFilteredDocumentCount(req, filters),
      getFilterOptionsWithCounts(req, filters),
    ]);

    return res.status(200).json({
      filtered_count: countResult.count,
      total_count: countResult.total,
      available_options: availableOptions,
    });
  } catch (error) {
    console.error('Failed to get preview:', error);
    return res.status(500).json({
      error: 'Internal server error',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
