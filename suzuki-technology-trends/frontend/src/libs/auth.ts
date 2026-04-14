/**
 * Authentication utilities for internal token handling.
 *
 * Internal token is a JWT that contains tenant_id and other claims.
 * The token is passed in the Authorization header from the gateway.
 */
import { decodeJwt } from 'jose';
import { IncomingMessage } from 'http';
import { NextApiRequest } from 'next';

const CADDI_ISSUER = 'https://caddi.internal';
const TENANT_ID_CLAIM = 'https://zoolake.jp/claims/tenantId';

/**
 * Extract the internal token from request headers.
 *
 * Priority:
 * 1. Authorization header (Bearer token)
 * 2. Environment variable (development only)
 */
export function getInternalTokenFromRequest(
  req: NextApiRequest | IncomingMessage
): string | null {
  // Try Authorization header first
  const authHeader = req.headers.authorization;
  if (authHeader && authHeader.startsWith('Bearer ')) {
    return authHeader.slice(7);
  }

  // Fallback to environment variable (development only)
  if (process.env.NODE_ENV !== 'production' && process.env.INTERNAL_TOKEN) {
    console.debug('Using INTERNAL_TOKEN from environment (development mode)');
    return process.env.INTERNAL_TOKEN;
  }

  return null;
}

/**
 * Decode JWT and extract tenant_id.
 *
 * Note: This does NOT verify the signature. Signature verification
 * should be done at the gateway level.
 */
export function getTenantIdFromToken(token: string): string | null {
  try {
    const payload = decodeJwt(token);

    // Verify this is a CADDI internal token
    if (payload.iss !== CADDI_ISSUER) {
      console.warn(`JWT issuer mismatch: expected ${CADDI_ISSUER}, got ${payload.iss}`);
      return null;
    }

    const tenantId = (payload[TENANT_ID_CLAIM] as string) ?? null;
    if (!tenantId) {
      console.warn(`JWT missing tenant_id claim: ${TENANT_ID_CLAIM}`);
    }
    return tenantId;
  } catch (error) {
    console.warn('Failed to decode JWT token:', error);
    return null;
  }
}

/**
 * Get tenant_id from request headers.
 * Combines token extraction and decoding.
 */
export function getTenantIdFromRequest(
  req: NextApiRequest | IncomingMessage
): string | null {
  const token = getInternalTokenFromRequest(req);
  if (!token) {
    return null;
  }
  return getTenantIdFromToken(token);
}

/**
 * Build authentication headers for downstream API calls.
 */
export function buildAuthHeaders(
  req: NextApiRequest | IncomingMessage
): Record<string, string> {
  const headers: Record<string, string> = {};

  const token = getInternalTokenFromRequest(req);
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Add x-caddi-tenant-id header for ISP (for local development)
  if (process.env.NODE_ENV !== 'production') {
    const tenantId = getTenantIdFromRequest(req);
    if (tenantId) {
      headers['x-caddi-tenant-id'] = tenantId;
    }
  }

  // Cloudflare Access headers (if configured)
  if (process.env.CF_ACCESS_CLIENT_ID) {
    headers['CF-Access-Client-Id'] = process.env.CF_ACCESS_CLIENT_ID;
  }
  if (process.env.CF_ACCESS_CLIENT_SECRET) {
    headers['CF-Access-Client-Secret'] = process.env.CF_ACCESS_CLIENT_SECRET;
  }

  return headers;
}
