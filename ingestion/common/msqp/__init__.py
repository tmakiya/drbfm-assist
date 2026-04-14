"""MSQP (Trino) client module for data ingestion."""

from .client import MSQPClient, create_msqp_client_from_env

__all__ = ["MSQPClient", "create_msqp_client_from_env"]
