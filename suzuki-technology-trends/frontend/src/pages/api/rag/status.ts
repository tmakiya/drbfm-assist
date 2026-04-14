/**
 * GET /api/rag/status
 *
 * Get RAG system status (document count, index info).
 */
import type { NextApiRequest, NextApiResponse } from 'next';
import { getRagStatus } from '../../../libs/isp-client';
import { getInternalTokenFromRequest } from '../../../libs/auth';

interface RagStatusResponse {
  status: 'active' | 'error';
  indexed_documents: number;
  index_alias: string;
  backend: string;
  error?: string;
}

interface ErrorResponse {
  error: string;
  detail?: string;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<RagStatusResponse | ErrorResponse>
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
    const status = await getRagStatus(req);
    return res.status(200).json(status);
  } catch (error) {
    console.error('Failed to get RAG status:', error);
    return res.status(500).json({
      error: 'Internal server error',
      detail: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}
