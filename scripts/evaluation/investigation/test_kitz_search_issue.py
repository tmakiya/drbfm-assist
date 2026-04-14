import logging
import json
import sys
import os
from dotenv import load_dotenv

# Add the project root to the Python path to resolve the module not found error
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from drassist.chains.drbfm_assist import (
    DrbfmAssistWorkflow,
    DrbfmAssistWorkflowState,
    DrbfmWorkflowContext,
)

# Configure logging to show debug information
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('drassist')
logger.setLevel(logging.DEBUG)


def main():
    """
    Runs a test of the DRBFM assist workflow to investigate a search issue.
    This script simulates the input that failed in the Streamlit app and
    logs detailed information about the workflow's execution, including
    extracted attributes and search results.
    """
    load_dotenv()

    # --- Input Data from the user's report ---
    # This is the input that caused the issue.
    input_part = "ステムベアリング"
    input_raw_change = "ステムベアリングの全長変更"
    
    # --- Workflow Configuration ---
    # These settings are taken from app_kitz.py
    config_path = "configs/70aaacd2.yaml"
    gemini_model = "gemini-2.5-pro"
    
    # Workflow context parameters
    top_k = 5
    search_size = 20

    logging.info("Starting DRBFM Assist Workflow test...")
    logging.info(f"Input Part: {input_part}")
    logging.info(f"Input Change: {input_raw_change}")

    # --- Initialize and Run Workflow ---
    try:
        # Get the compiled workflow
        drbfm_assist_workflow = DrbfmAssistWorkflow(
            config_path=config_path,
            gemini_model_name=gemini_model,
            product_segment=None  # As per the default in the app
        ).compile()

        # Set up the initial state and context for the workflow
        initial_state = DrbfmAssistWorkflowState(raw_input=input_raw_change, part=input_part)
        context = DrbfmWorkflowContext(top_k=top_k, search_size=search_size)

        logging.info("Invoking the workflow...")
        
        # This is where the magic happens. We run the entire process.
        result = drbfm_assist_workflow.invoke(initial_state, context=context)

        logging.info("Workflow execution finished.")
        
        # --- Log the Results for Analysis ---
        logging.info("\n" + "="*30 + " WORKFLOW RESULTS " + "="*30)
        
        if result.get("error"):
            logging.error(f"Workflow terminated with an error: {result['error']}")

        per_cp_results = result.get("per_cp_results", [])
        if not per_cp_results:
            logging.warning("No results were generated for any change point.")
        
        for i, cp_result in enumerate(per_cp_results):
            logging.info(f"\n--- Analysis for Change Point {i+1}: '{cp_result.get('change_point')}' ---")
            
            # Log the critical extracted attributes that are used for the search
            attributes = cp_result.get('change_point_attributes')
            if attributes:
                logging.info("Extracted Query Attributes:")
                logging.info(f"  - Unit: {attributes.unit}")
                logging.info(f"  - Parts: {attributes.parts}")
                logging.info(f"  - Change: {attributes.change}")
            else:
                logging.warning("Could not extract query attributes.")

            # Log the search history to see what queries were run
            search_history = cp_result.get('search_history', [])
            if search_history:
                logging.info("Search History:")
                for entry in search_history:
                    logging.info(f"  - Stage {entry['stage']} ({entry['method']}): Found {entry['result_count']} results.")
            
            # Log the final relevant search results
            search_results = cp_result.get("relevant_search_results", [])
            logging.info(f"Final number of relevant search results: {len(search_results)}")

            if not search_results:
                logging.warning("No relevant documents were found for this change point.")
            else:
                logging.info("Found relevant documents:")
                for doc in search_results:
                    logging.info(f"  - Doc ID: {doc.get('doc_id')}, Score: {doc.get('score')}, Title: {doc.get('title')}")

    except Exception as e:
        logging.error(f"An unexpected error occurred during the test run: {e}", exc_info=True)


if __name__ == "__main__":
    main()
