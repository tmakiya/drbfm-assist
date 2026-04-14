/**
 * ISP (Interactive Search Platform) client for filter retrieval.
 *
 * This module provides direct ISP API access for:
 * - Filter options aggregation
 * - Document count preview
 */
import { IncomingMessage } from 'http';
import { NextApiRequest } from 'next';
import { buildAuthHeaders, getTenantIdFromRequest } from './auth';

// Environment configuration
const ISP_URL = process.env.ISP_URL || 'http://localhost:50080';
const ISP_INDEX_NAME = process.env.ISP_INDEX_NAME || 'suzuki-technology-trends';

/**
 * Get the tenant-specific index alias.
 */
function getIndexAlias(tenantId: string | null): string {
  if (tenantId) {
    return `${ISP_INDEX_NAME}_${tenantId}`;
  }
  return ISP_INDEX_NAME;
}

/**
 * Filter options returned from ISP aggregation.
 */
export interface FilterOptions {
  projects: string[];
  technologies: string[];
  issues: string[];
  components: string[];
}

/**
 * Filter option with document count.
 */
export interface FilterOptionWithCount {
  key: string;
  doc_count: number;
}

/**
 * Filter options with document counts returned from ISP aggregation.
 */
export interface FilterOptionsWithCounts {
  projects: FilterOptionWithCount[];
  technologies: FilterOptionWithCount[];
  issues: FilterOptionWithCount[];
  components: FilterOptionWithCount[];
}

/**
 * Get available filter options from ISP using aggregation query.
 * Returns options with document counts for each option.
 */
export async function getFilterOptions(
  req: NextApiRequest | IncomingMessage
): Promise<FilterOptionsWithCounts> {
  const tenantId = getTenantIdFromRequest(req);
  const alias = getIndexAlias(tenantId);
  const headers = buildAuthHeaders(req);

  // ISP document fields: project, technology_theme, issue_theme, components_theme
  const aggregationQuery = {
    size: 0,
    aggs: {
      projects: {
        terms: { field: 'project', size: 1000 },
      },
      technologies: {
        terms: { field: 'technology_theme', size: 1000 },
      },
      issues: {
        terms: { field: 'issue_theme', size: 1000 },
      },
      components: {
        terms: { field: 'components_theme', size: 1000 },
      },
    },
  };

  try {
    const response = await fetch(`${ISP_URL}/${alias}/_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify(aggregationQuery),
    });

    if (!response.ok) {
      throw new Error(`ISP request failed: ${response.status}`);
    }

    const result = await response.json();
    const aggs = result.aggregations || {};

    return {
      projects: extractBucketKeysWithCounts(aggs.projects),
      technologies: extractBucketKeysWithCounts(aggs.technologies),
      issues: extractBucketKeysWithCounts(aggs.issues),
      components: extractBucketKeysWithCounts(aggs.components),
    };
  } catch (error) {
    console.error('Failed to get filter options from ISP:', error);
    return {
      projects: [],
      technologies: [],
      issues: [],
      components: [],
    };
  }
}

/**
 * Extract keys from aggregation buckets.
 */
function extractBucketKeys(
  agg: { buckets?: Array<{ key: string }> } | undefined
): string[] {
  if (!agg?.buckets) {
    return [];
  }
  return agg.buckets.map((bucket) => bucket.key).filter(Boolean);
}

/**
 * Values to exclude from filter options.
 * These are typically placeholder values for documents without a proper theme assigned.
 */
const EXCLUDED_FILTER_VALUES = ['なし'];

/**
 * Extract keys with counts from aggregation buckets.
 */
function extractBucketKeysWithCounts(
  agg: { buckets?: Array<{ key: string; doc_count: number }> } | undefined
): FilterOptionWithCount[] {
  if (!agg?.buckets) {
    return [];
  }
  return agg.buckets
    .filter((bucket) => bucket.key && !EXCLUDED_FILTER_VALUES.includes(bucket.key))
    .map((bucket) => ({ key: bucket.key, doc_count: bucket.doc_count }));
}

/**
 * Get available filter options with document counts from ISP using aggregation query.
 * This filters the aggregation based on current filter selections.
 */
export async function getFilterOptionsWithCounts(
  req: NextApiRequest | IncomingMessage,
  filters: FilterCriteria
): Promise<FilterOptionsWithCounts> {
  const tenantId = getTenantIdFromRequest(req);
  const alias = getIndexAlias(tenantId);
  const headers = buildAuthHeaders(req);

  // Build filter query based on current selections
  const mustClauses: Array<Record<string, unknown>> = [];

  if (filters.project_keywords?.length) {
    mustClauses.push({ terms: { project: filters.project_keywords } });
  }
  if (filters.tech_keywords?.length) {
    mustClauses.push({ terms: { technology_theme: filters.tech_keywords } });
  }
  if (filters.interest_keywords?.length) {
    mustClauses.push({ terms: { issue_theme: filters.interest_keywords } });
  }
  if (filters.component_keywords?.length) {
    mustClauses.push({ terms: { components_theme: filters.component_keywords } });
  }

  const query =
    mustClauses.length > 0 ? { bool: { must: mustClauses } } : { match_all: {} };

  // ISP document fields: project, technology_theme, issue_theme, components_theme
  const aggregationQuery = {
    size: 0,
    query,
    aggs: {
      projects: {
        terms: { field: 'project', size: 1000 },
      },
      technologies: {
        terms: { field: 'technology_theme', size: 1000 },
      },
      issues: {
        terms: { field: 'issue_theme', size: 1000 },
      },
      components: {
        terms: { field: 'components_theme', size: 1000 },
      },
    },
  };

  try {
    const response = await fetch(`${ISP_URL}/${alias}/_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify(aggregationQuery),
    });

    if (!response.ok) {
      throw new Error(`ISP request failed: ${response.status}`);
    }

    const result = await response.json();
    const aggs = result.aggregations || {};

    return {
      projects: extractBucketKeysWithCounts(aggs.projects),
      technologies: extractBucketKeysWithCounts(aggs.technologies),
      issues: extractBucketKeysWithCounts(aggs.issues),
      components: extractBucketKeysWithCounts(aggs.components),
    };
  } catch (error) {
    console.error('Failed to get filter options with counts from ISP:', error);
    return {
      projects: [],
      technologies: [],
      issues: [],
      components: [],
    };
  }
}

/**
 * Filter criteria for document count preview.
 */
export interface FilterCriteria {
  interest_keywords?: string[];
  tech_keywords?: string[];
  component_keywords?: string[];
  project_keywords?: string[];
}

/**
 * Get document count with applied filters.
 * Uses _search with size: 0 since ISP doesn't support _count endpoint.
 */
export async function getFilteredDocumentCount(
  req: NextApiRequest | IncomingMessage,
  filters: FilterCriteria
): Promise<{ count: number; total: number }> {
  const tenantId = getTenantIdFromRequest(req);
  const alias = getIndexAlias(tenantId);
  const headers = buildAuthHeaders(req);

  // Build filter query
  // ISP document fields: project, technology_theme, issue_theme, components_theme
  const mustClauses: Array<Record<string, unknown>> = [];

  if (filters.project_keywords?.length) {
    mustClauses.push({ terms: { project: filters.project_keywords } });
  }
  if (filters.tech_keywords?.length) {
    mustClauses.push({ terms: { technology_theme: filters.tech_keywords } });
  }
  if (filters.interest_keywords?.length) {
    mustClauses.push({ terms: { issue_theme: filters.interest_keywords } });
  }
  if (filters.component_keywords?.length) {
    mustClauses.push({ terms: { components_theme: filters.component_keywords } });
  }

  const query =
    mustClauses.length > 0
      ? { bool: { must: mustClauses } }
      : { match_all: {} };

  try {
    // Get filtered count using _search with size: 0
    const countResponse = await fetch(`${ISP_URL}/${alias}/_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({ size: 0, query }),
    });

    if (!countResponse.ok) {
      throw new Error(`ISP search request failed: ${countResponse.status}`);
    }

    const countResult = await countResponse.json();

    // Get total count using _search with size: 0
    const totalResponse = await fetch(`${ISP_URL}/${alias}/_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({ size: 0, query: { match_all: {} } }),
    });

    if (!totalResponse.ok) {
      throw new Error(`ISP total search request failed: ${totalResponse.status}`);
    }

    const totalResult = await totalResponse.json();

    // ISP returns hits.total as integer (not object like ES)
    return {
      count: countResult.hits?.total ?? 0,
      total: totalResult.hits?.total ?? 0,
    };
  } catch (error) {
    console.error('Failed to get document count from ISP:', error);
    return { count: 0, total: 0 };
  }
}

/**
 * Get RAG system status (document count and index info).
 * Uses _search with size: 0 since ISP doesn't support _count endpoint.
 */
export async function getRagStatus(
  req: NextApiRequest | IncomingMessage
): Promise<{
  status: 'active' | 'error';
  indexed_documents: number;
  index_alias: string;
  backend: string;
  error?: string;
}> {
  const tenantId = getTenantIdFromRequest(req);
  const alias = getIndexAlias(tenantId);
  const headers = buildAuthHeaders(req);

  try {
    // Use _search with size: 0 to get total count (ISP doesn't support _count)
    const response = await fetch(`${ISP_URL}/${alias}/_search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: JSON.stringify({
        size: 0,
        query: { match_all: {} },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`ISP status request failed: ${response.status}`, errorText);
      return {
        status: 'error',
        indexed_documents: 0,
        index_alias: alias,
        backend: 'isp',
        error: `ISP request failed: ${response.status}`,
      };
    }

    const result = await response.json();
    // ISP returns hits.total as integer (not object like ES)
    const total = result.hits?.total ?? 0;

    return {
      status: 'active',
      indexed_documents: total,
      index_alias: alias,
      backend: 'isp',
    };
  } catch (error) {
    console.error('Failed to get RAG status from ISP:', error);
    return {
      status: 'error',
      indexed_documents: 0,
      index_alias: alias,
      backend: 'isp',
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

export { ISP_URL, ISP_INDEX_NAME };
