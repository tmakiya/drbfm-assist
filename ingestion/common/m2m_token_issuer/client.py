"""M2M Token Issuer client for OAuth2 Client Credentials authentication."""

import base64
import json
import os

import requests
from loguru import logger


class M2MTokenIssuerClient:
    """Client for M2M Token Issuer to obtain Internal Tokens."""

    def __init__(
        self,
        base_url: str = "http://m2m-token-issuer.cp.internal.caddi.io",
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False

    def get_internal_token(self, tenant_id: str) -> str:
        """Obtain an Internal Token for the specified tenant.

        Args:
            tenant_id: Target tenant ID

        Returns:
            Internal Token (JWT)

        Raises:
            ValueError: If client_id or client_secret is not set
            requests.HTTPError: If the API request fails

        """
        if not self.client_id or not self.client_secret:
            raise ValueError("client_id and client_secret are required")

        # Create Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        auth_header = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        body = {
            "grant_type": "client_credentials",
            "tenant_id": tenant_id,
        }

        logger.debug(
            f"Requesting Internal Token from M2M Token Issuer: "
            f"tenant_id={tenant_id}, client_id={self.client_id}"
        )

        response = self.session.post(
            f"{self.base_url}/oauth2/internal-token",
            data=body,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            logger.error(f"Failed to obtain Internal Token: {response.status_code} - {response.text}")

        response.raise_for_status()
        result = response.json()

        access_token = result.get("access_token")
        if not access_token:
            raise ValueError("access_token not found in response")

        # Validate tenant_id from token matches environment variable
        expected_tenant_id = os.getenv("TENANT_ID")
        actual_tenant_id = self.get_tenant_id_from_token(access_token)

        if actual_tenant_id == expected_tenant_id:
            logger.info(f"Tenant ID validation successful: {actual_tenant_id}")
        else:
            raise ValueError(
                f"Tenant ID mismatch: token contains '{actual_tenant_id}', "
                f"but TENANT_ID env var is '{expected_tenant_id}'"
            )

        logger.debug("Successfully obtained Internal Token")
        return access_token

    @staticmethod
    def get_tenant_id_from_token(token: str) -> str:
        """Extract tenant_id from Internal Token (JWT).

        Args:
            token: Internal Token (JWT string)

        Returns:
            Tenant ID extracted from the token

        Raises:
            ValueError: If the token is invalid or tenant_id is not found

        """
        try:
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("Invalid JWT format: expected 3 parts separated by '.'")

            # Decode payload (add padding if needed for base64 decoding)
            payload = parts[1]
            # Add padding to make length a multiple of 4
            padding = len(payload) % 4
            if padding:
                payload += "=" * (4 - padding)

            decoded_bytes = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded_bytes)
            logger.debug(f"JWT claims keys: {list(claims.keys())}")

            tenant_id = claims.get("https://zoolake.jp/claims/tenantId")
            if not tenant_id:
                logger.info(f"JWT claims keys: {list(claims.keys())}")
                raise ValueError("tenant_id not found in token claims")

            logger.info(f"Extracted tenant_id from token: {tenant_id}")
            return tenant_id

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to decode JWT token: {e}") from e


def create_m2m_token_issuer_client_from_env() -> M2MTokenIssuerClient:
    """Create M2M Token Issuer client from environment variables.

    Environment variables:
        M2M_TOKEN_ISSUER_URL: M2M Token Issuer base URL (optional)
        M2M_INTERNAL_TOKEN_CLIENT_ID: Client ID for Internal Token
        M2M_INTERNAL_TOKEN_CLIENT_SECRET: Client Secret for Internal Token

    Returns:
        M2MTokenIssuerClient instance

    """
    base_url = os.getenv(
        "M2M_TOKEN_ISSUER_URL",
        "http://m2m-token-issuer.cp.internal.caddi.io",
    )
    client_id = os.getenv("M2M_INTERNAL_TOKEN_CLIENT_ID")
    client_secret = os.getenv("M2M_INTERNAL_TOKEN_CLIENT_SECRET")

    logger.info(
        f"M2M Token Issuer client: url={base_url}, "
        f"has_client_id={bool(client_id)}, has_client_secret={bool(client_secret)}"
    )

    return M2MTokenIssuerClient(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
    )
