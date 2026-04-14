"""Base classes for LangGraph implementations"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

load_dotenv()


class BaseGraphState(BaseModel):
    """Base state for all LangGraph workflows"""

    error: Optional[str] = Field(default=None, description="Error message if any")


class BaseGraph(ABC):
    """Base class for LangGraph implementations"""

    def __init__(self, config_path: str, gemini_model_name: str = "gemini-2.5-flash"):
        self._compiled_workflow = None
        self._config_path = config_path
        self._gemini_model_name = gemini_model_name
        self._config_manager = None
        self._gemini_client = None
        self._langsmith_client = None
        self._es_manager = None

    @property
    @abstractmethod
    def state_class(self) -> type[BaseModel]:
        """Return the state class for this graph"""
        pass

    @abstractmethod
    def create_workflow(self) -> StateGraph:
        """Create and configure the workflow graph"""
        pass

    def compile(self) -> StateGraph:
        """Compile the workflow graph"""
        if self._compiled_workflow is None:
            workflow = self.create_workflow()
            self._compiled_workflow = workflow.compile()
        return self._compiled_workflow

    def run(
        self, initial_state: BaseModel, config: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Run the workflow with given initial state"""
        compiled_workflow = self.compile()
        final_event = None

        for event in compiled_workflow.stream(
            initial_state, config=config, stream_mode="values"
        ):
            final_event = event

        return final_event

    def stream(self, initial_state: BaseModel, config: Optional[Dict[str, Any]] = None):
        """Stream the workflow execution"""
        compiled_workflow = self.compile()
        return compiled_workflow.stream(
            initial_state, config=config, stream_mode="values"
        )

    def invoke(
        self, initial_state: BaseModel, config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Invoke the workflow with given initial state and return final state"""
        compiled_workflow = self.compile()
        return compiled_workflow.invoke(initial_state, config=config)

    @property
    def config_manager(self):
        """Get or create ConfigManager instance"""
        if self._config_manager is None:
            from drassist.config.manager import ConfigManager

            self._config_manager = ConfigManager(self._config_path)
        return self._config_manager

    @property
    def gemini_client(self):
        """Get or create GeminiClient instance"""
        if self._gemini_client is None:
            from drassist.llm import GeminiClient

            self._gemini_client = GeminiClient(
                model_name=self._gemini_model_name,
                location="us-central1",
                temperature=0.0,
                seed=42,
            )
        return self._gemini_client

    @property
    def langsmith_client(self):
        """Get or create Langsmith client instance"""
        if self._langsmith_client is None:
            from langsmith import Client

            # Build headers for Cloudflare Access authentication
            headers: Dict[str, str] = {}
            cf_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
            cf_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
            if cf_client_id:
                headers["CF-Access-Client-Id"] = cf_client_id
            if cf_client_secret:
                headers["CF-Access-Client-Secret"] = cf_client_secret

            self._langsmith_client = Client(headers=headers if headers else None)
        return self._langsmith_client

    @property
    def isp_manager(self):
        """Get or create ISPManager instance"""
        if self._es_manager is None:
            from drassist.isp.manager import ISPManager

            self._es_manager = ISPManager(self.config_manager)
        return self._es_manager

    # Alias for backward compatibility
    @property
    def es_manager(self):
        """Alias for isp_manager (backward compatibility)"""
        return self.isp_manager
