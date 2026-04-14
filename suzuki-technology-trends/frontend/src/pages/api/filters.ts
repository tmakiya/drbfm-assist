/**
 * GET /api/filters
 *
 * Get available filter options from ISP.
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import { getFilterOptions, FilterOptionsWithCounts } from '../../libs/isp-client';
import { getInternalTokenFromRequest } from '../../libs/auth';

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<FilterOptionsWithCounts | ErrorResponse>
) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', ['GET']);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Check authentication
  const token = getInternalTokenFromRequest(req);
  if (!token && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const filters = await getFilterOptions(req);

    // Transform to match existing frontend expectations
    // The frontend expects: { 課題テーマ: [...], 技術テーマ: [...], ... }
    return res.status(200).json({
      projects: filters.projects,
      technologies: filters.technologies,
      issues: filters.issues,
      components: filters.components,
    });
  } catch (error) {
    console.error('Failed to get filters:', error);
    return res.status(500).json({
      error: 'Internal server error',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
