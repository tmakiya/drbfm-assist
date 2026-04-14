import logging
import sys
import os
import pandas as pd
from dotenv import load_dotenv

# Add the project root to the Python path to resolve module not found errors
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from drassist.chains.drbfm_assist import (
    DrbfmAssistWorkflow,
    DrbfmAssistWorkflowState,
    DrbfmWorkflowContext,
)
# Import the function we want to test from the streamlit app
from app_kitz import create_output_df

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('drassist')
# Keep drassist logs quieter for this test, as we are focused on the final output
logger.setLevel(logging.WARNING)


def main():
    """
    Runs the DRBFM assist workflow and then processes the results using the
    create_output_df function from app_kitz.py to show the final formatted output.
    """
    load_dotenv()

    # --- Input Data ---
    # Using the "ボデー" case as the test input
    inputs_to_process = [{
        "part": "ボデー",
        "raw_input": "機種変更 新: ボデー　150SCHBSL(新規)  旧: ボデー　300SCHBSL"
    }]
    
    # --- Workflow Configuration ---
    config_path = "configs/70aaacd2.yaml"
    gemini_model = "gemini-2.5-pro"
    
    # Workflow context parameters
    top_k = 5
    search_size = 20

    logging.info("Starting DRBFM Assist Workflow to get results...")
    
    try:
        # --- 1. Run the workflow to get the raw 'results' object ---
        drbfm_assist_workflow = DrbfmAssistWorkflow(
            config_path=config_path,
            gemini_model_name=gemini_model,
            product_segment=None
        ).compile()

        initial_state = DrbfmAssistWorkflowState(
            raw_input=inputs_to_process[0]["raw_input"], 
            part=inputs_to_process[0]["part"]
        )
        context = DrbfmWorkflowContext(top_k=top_k, search_size=search_size)
        
        # We need to wrap the result in a list to match the structure app_kitz expects
        results = [drbfm_assist_workflow.invoke(initial_state, context=context)]
        logging.info("Workflow execution finished.")
        
        # --- 2. Pass the results to the create_output_df function ---
        logging.info("\nProcessing results with create_output_df from app_kitz.py...")
        
        # This function creates the final DataFrame for display
        output_df = create_output_df(inputs_to_process, results)
        
        # --- 3. Print the final DataFrame ---
        logging.info("Generated Output DataFrame (output_rows):")
        
        # Configure pandas to display all columns and prevent truncation
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', None)
        
        print(output_df)

    except Exception as e:
        logging.error(f"An unexpected error occurred during the test run: {e}", exc_info=True)


if __name__ == "__main__":
    main()
