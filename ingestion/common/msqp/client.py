"""MSQP (Trino) client for data ingestion."""

import base64
import json
import os
from uuid import UUID

import polars as pl
import requests
from loguru import logger
from trino.auth import JWTAuthentication
from trino.dbapi import connect


class MSQPClient:
    """Client for MSQP (Trino) queries with JWT authentication."""

    def __init__(
        self,
        host: str,
        tenant_id: str,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        catalog: str = "drawing",
        schema: str = "msqp__drawing",
        port: int = 443,
        http_scheme: str = "https",
        local_mode: bool = False,
    ):
        self.host = host
        self.tenant_id = tenant_id
        self.catalog = catalog
        self.schema = schema
        self.port = port
        self.http_scheme = http_scheme
        self.local_mode = local_mode

        if access_token:
            self.access_token = access_token
        elif client_id and client_secret:
            self.access_token = self._obtain_token(client_id, client_secret)
        else:
            raise ValueError("Either access_token or (client_id, client_secret) required")

        logger.info(f"MSQP client: {http_scheme}://{host}:{port}, local={local_mode}")

    def _obtain_token(self, client_id: str, client_secret: str) -> str:
        """Obtain JWT access token using client credentials."""
        auth_url = self._get_auth_url()
        proxies = self._get_proxies()
        verify_ssl = os.getenv("MSQP_VERIFY_SSL", "true").lower() == "true"

        response = requests.post(
            auth_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "tenant_id": self.tenant_id,
                "email": f"{client_id}@client",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
            verify=verify_ssl,
            proxies=proxies if proxies else None,
        )

        if response.status_code != 200:
            raise Exception(f"Token acquisition failed: {response.status_code} - {response.text}")

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise Exception("Access token not found in response")

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

        logger.info("Successfully obtained access token")
        return access_token

    def _get_auth_url(self) -> str:
        """Determine auth URL from environment or host."""
        if auth_url := os.getenv("MSQP_AUTH_URL"):
            return auth_url

        if "internal.caddi.io" in self.host:
            return "https://msqp-auth.dp.internal.caddi.io/oauth2/token"
        elif "dev-msqp-trino" in self.host:
            return "https://dev-msqp-auth.zoolake.jp/oauth2/token"
        elif "stg-msqp-trino" in self.host:
            return "https://stg-msqp-auth.zoolake.jp/oauth2/token"
        elif "prod-msqp-trino" in self.host:
            return "https://prod-msqp-auth.zoolake.jp/oauth2/token"
        else:
            raise ValueError("Cannot determine MSQP_AUTH_URL from host")

    def _get_proxies(self) -> dict[str, str] | None:
        """Get proxy configuration based on local_mode."""
        if not self.local_mode:
            return None
        proxy_url = os.getenv("HTTPS_PROXY", "socks5h://localhost:1080")
        return {"https": proxy_url, "http": proxy_url}

    def _get_connection(self):
        """Get Trino database connection."""
        verify_ssl = os.getenv("MSQP_VERIFY_SSL", "true").lower() == "true"

        http_session = requests.Session()
        http_session.verify = verify_ssl
        if proxies := self._get_proxies():
            http_session.proxies = proxies

        return connect(
            host=self.host,
            port=self.port,
            user=self.access_token,
            catalog=self.catalog,
            schema=self.schema,
            http_scheme=self.http_scheme,
            auth=JWTAuthentication(self.access_token),
            http_session=http_session,
        )

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

            tenant_id = claims.get("tenant_id")
            if not tenant_id:
                logger.info(f"JWT claims keys: {list(claims.keys())}")
                raise ValueError("tenant_id not found in token claims")

            logger.info(f"Extracted tenant_id from token: {tenant_id}")
            return tenant_id

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Failed to decode JWT token: {e}") from e

    def query(self, sql: str) -> pl.DataFrame:
        """Execute SQL query and return results as DataFrame."""
        logger.info(f"Executing query:\n{sql[:100000]}")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            logger.info(f"Query fetched {len(rows)} rows with columns: {columns}")

            if not rows:
                # Return empty DataFrame with column names
                return pl.DataFrame({col: [] for col in columns})

            # Build DataFrame column by column to handle types properly
            # Convert UUID to string for Polars compatibility
            def convert_value(val):
                if isinstance(val, UUID):
                    return str(val)
                return val

            data = {col: [convert_value(row[i]) for row in rows] for i, col in enumerate(columns)}
            df = pl.DataFrame(data)

            logger.info(f"Query returned {len(df)} rows")
            return df
        finally:
            conn.close()

    def execute(self, sql: str) -> None:
        """Execute SQL statement without returning results."""
        logger.info(f"Executing statement:\n{sql[:100000]}")

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            logger.info("Statement executed successfully")
        finally:
            conn.close()

    def use(self, catalog: str | None = None, schema: str | None = None) -> None:
        """Change the current catalog and/or schema."""
        if not catalog and not schema:
            raise ValueError("At least one of catalog or schema must be provided")

        if catalog and schema:
            schema_quoted = f'"{schema}"' if "-" in schema or " " in schema else schema
            sql = f"USE {catalog}.{schema_quoted}"
            self.catalog = catalog
            self.schema = schema
        elif catalog:
            sql = f"USE {catalog}"
            self.catalog = catalog
        else:
            schema_quoted = f'"{schema}"' if "-" in schema or " " in schema else schema
            sql = f"USE {schema_quoted}"
            self.schema = schema

        self.execute(sql)

    def list_tables(self, catalog: str | None = None, schema: str | None = None) -> list[str]:
        """List tables in a schema."""
        target_catalog = catalog or self.catalog
        target_schema = schema or self.schema
        sql = f'SHOW TABLES FROM {target_catalog}."{target_schema}"'
        df = self.query(sql)
        return df["Table"].to_list() if "Table" in df.columns else []

    def table_exists(self, table_name: str, catalog: str | None = None, schema: str | None = None) -> bool:
        """Check if a table exists."""
        return table_name in self.list_tables(catalog, schema)

    def get_table_schema(
        self, table_name: str, catalog: str | None = None, schema: str | None = None
    ) -> pl.DataFrame:
        """Get table schema information."""
        target_catalog = catalog or self.catalog
        target_schema = schema or self.schema
        sql = f'DESCRIBE {target_catalog}."{target_schema}".{table_name}'
        return self.query(sql)


def create_msqp_client_from_env(local_mode: bool | None = None) -> MSQPClient:
    """Create MSQP client from environment variables."""
    if local_mode is None:
        local_mode = os.getenv("LOCAL_MODE", "false").lower() == "true"

    tenant_id = os.getenv("TENANT_ID")
    if not tenant_id:
        raise ValueError("TENANT_ID environment variable is required")

    return MSQPClient(
        host=os.getenv("MSQP_HOST", "msqp.dp.internal.caddi.io"),
        tenant_id=tenant_id,
        access_token=os.getenv("MSQP_ACCESS_TOKEN"),
        client_id=os.getenv("MSQP_CLIENT_ID"),
        client_secret=os.getenv("MSQP_CLIENT_SECRET"),
        catalog=os.getenv("MSQP_CATALOG", "drawing"),
        schema=os.getenv("MSQP_SCHEMA", "msqp__drawing"),
        local_mode=local_mode,
    )
