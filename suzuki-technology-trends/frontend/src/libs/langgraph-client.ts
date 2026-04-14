/**
 * LangGraph Platform client for workflow execution.
 *
 * This module provides a typed client for interacting with LangGraph Platform.
 * Pattern follows ui/src/client.py from the reference implementation.
 */
import { Client, type Run } from '@langchain/langgraph-sdk';
import { IncomingMessage } from 'http';
import { NextApiRequest } from 'next';
import { buildAuthHeaders, getTenantIdFromRequest } from './auth';

// RunStatus is not exported from the SDK, so we extract it from the Run type
type RunStatus = Run['status'];

// Environment configuration
const LANGGRAPH_SERVER_URL =
  process.env.LANGGRAPH_SERVER_URL || 'http://localhost:8123';
const LANGGRAPH_GRAPH_ID = process.env.LANGGRAPH_GRAPH_ID || 'drawer-ai';
const LANGGRAPH_API_KEY = process.env.LANGGRAPH_API_KEY;

export class LangGraphClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LangGraphClientError';
  }
}

/**
 * Create a LangGraph SDK client with proper authentication headers.
 */
export function getLangGraphClient(
  req: NextApiRequest | IncomingMessage
): Client {
  try {
    const headers = buildAuthHeaders(req);

    const client = new Client({
      apiUrl: LANGGRAPH_SERVER_URL,
      defaultHeaders: headers,
      apiKey: LANGGRAPH_API_KEY,
    });

    return client;
  } catch (error) {
    console.error('Failed to initialize LangGraph client:', error);
    throw new LangGraphClientError(
      `Failed to connect to LangGraph Platform: ${error}`
    );
  }
}

/**
 * Analysis request input for the workflow.
 */
export interface AnalysisInput {
  topic: string;
  use_case: string;
  interest_keywords: string[];
  tech_keywords: string[];
  component_keywords: string[];
  project_keywords: string[];
  additional_context?: string;
}

/**
 * Analysis workflow configuration.
 */
export interface AnalysisConfig {
  top_k?: number;
  search_size?: number;
}

/**
 * Response from starting an analysis workflow.
 */
export interface StartAnalysisResponse {
  job_id: string;
  thread_id: string;
  run_id: string;
  status: string;
}

/**
 * Start an analysis workflow.
 *
 * @param req - The incoming request (for auth headers)
 * @param input - The analysis input parameters
 * @param config - Optional workflow configuration
 * @returns The thread_id and run_id for tracking
 */
export async function startAnalysis(
  req: NextApiRequest | IncomingMessage,
  input: AnalysisInput,
  config?: AnalysisConfig
): Promise<{ threadId: string; runId: string }> {
  const client = getLangGraphClient(req);
  const tenantId = getTenantIdFromRequest(req);

  // Create a new thread with metadata
  const thread = await client.threads.create({
    metadata: {
      tenant_id: tenantId || 'default',
      created_at: new Date().toISOString(),
    },
  });

  // Start the workflow run
  const run = await client.runs.create(thread.thread_id, LANGGRAPH_GRAPH_ID, {
    input: {
      ...input,
      client_id: tenantId || 'default',
    },
    config: {
      configurable: {
        top_k: config?.top_k ?? 50,
        search_size: config?.search_size ?? 100,
      },
    },
  });

  return {
    threadId: thread.thread_id,
    runId: run.run_id,
  };
}

/**
 * Get the current state of a workflow run.
 */
export async function getRunState(
  req: NextApiRequest | IncomingMessage,
  threadId: string
): Promise<{
  status: string;
  values: Record<string, unknown>;
  next: string[];
}> {
  const client = getLangGraphClient(req);

  const state = await client.threads.getState(threadId);

  return {
    status: state.next?.length > 0 ? 'running' : 'completed',
    values: state.values as Record<string, unknown>,
    next: (state.next as string[]) || [],
  };
}

/**
 * Wait for a workflow run to complete.
 */
export async function waitForRun(
  req: NextApiRequest | IncomingMessage,
  threadId: string,
  runId: string
): Promise<void> {
  const client = getLangGraphClient(req);
  await client.runs.join(threadId, runId);
}

/**
 * Get the status of the latest run for a thread.
 * This is more reliable than checking state.next for determining completion status.
 */
export async function getLatestRunStatus(
  req: NextApiRequest | IncomingMessage,
  threadId: string
): Promise<{ status: RunStatus; runId: string } | null> {
  const client = getLangGraphClient(req);
  const runs = await client.runs.list(threadId, { limit: 1 });
  if (runs.length === 0) return null;
  return { status: runs[0].status, runId: runs[0].run_id };
}

/**
 * Get the status of a specific run by run_id.
 * This is faster than runs.list() as it directly fetches the run.
 */
export async function getRunStatus(
  req: NextApiRequest | IncomingMessage,
  threadId: string,
  runId: string
): Promise<{ status: RunStatus } | null> {
  const client = getLangGraphClient(req);
  const run = await client.runs.get(threadId, runId);
  if (!run) return null;
  return { status: run.status };
}

/**
 * Get the final result of a completed workflow.
 */
export async function getAnalysisResult(
  req: NextApiRequest | IncomingMessage,
  threadId: string
): Promise<{
  expert_team: Array<{ name: string; persona: string }>;
  final_report: string;
  references: Array<Record<string, unknown>>;
  messages: Array<Record<string, unknown>>;
}> {
  const client = getLangGraphClient(req);

  const state = await client.threads.getState(threadId);
  const values = state.values as Record<string, unknown>;

  return {
    expert_team: (values.expert_team as Array<{ name: string; persona: string }>) || [],
    final_report: (values.final_report as string) || '',
    references: (values.references as Array<Record<string, unknown>>) || [],
    messages: (values.messages as Array<Record<string, unknown>>) || [],
  };
}

export { LANGGRAPH_GRAPH_ID, LANGGRAPH_SERVER_URL };
