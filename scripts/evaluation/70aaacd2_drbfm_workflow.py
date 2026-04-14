import asyncio
import logging
import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from drassist.chains.drbfm_assist import (
    DrbfmAssistWorkflow,
    DrbfmAssistWorkflowState,
    DrbfmWorkflowContext,
)
from dotenv import load_dotenv

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

load_dotenv()

async def main():
    """Run the DRBFM assist workflow directly."""
    workflow = DrbfmAssistWorkflow(
        config_path="configs/70aaacd2.yaml",
        gemini_model_name="gemini-1.5-pro",
    )

    initial_state = DrbfmAssistWorkflowState(
        raw_input="ライニングの変更",
        part="ボデー",
    )

    context = DrbfmWorkflowContext(top_k=5, search_size=20)

    compiled_workflow = workflow.compile()

    try:
        # Use ainvoke since the underlying implementation uses async
        logging.info("Starting DRBFM workflow...")
        result = await compiled_workflow.ainvoke(initial_state, {"context": context})
        logging.info("Workflow finished. Result:")
        logging.info(result)
    except Exception as e:
        import traceback
        logging.error("An error occurred during workflow execution:")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
