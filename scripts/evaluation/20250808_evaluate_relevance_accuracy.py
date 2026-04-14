#!/usr/bin/env python3
"""Relevance Evaluation Accuracy Assessment Script
Evaluates the accuracy of _evaluate_single_result() function by comparing
LLM predictions with ground truth labels from evaluation CSV.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import get_client
from loguru import logger
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from drassist.config.manager import ConfigManager
from drassist.elasticsearch.manager import ElasticsearchManager
from drassist.llm.gemini_client import GeminiClient

load_dotenv()


def generate_timestamp_suffix() -> str:
    """Generate timestamp suffix in YYYYMMDD-HHMM format"""
    return datetime.now().strftime("%Y%m%d-%H%M")


def generate_label(ground_truth: bool, prediction: Optional[bool]) -> str:
    """Generate TP/FP/TN/FN label based on ground truth and prediction"""
    if prediction is None:
        return "ERROR"

    if ground_truth and prediction:
        return "TP"
    elif not ground_truth and prediction:
        return "FP"
    elif not ground_truth and not prediction:
        return "TN"
    else:  # ground_truth and not prediction
        return "FN"


class RelevanceEvaluator:
    """Evaluates relevance evaluation accuracy"""

    def __init__(self, config_path: str = "configs/6307204b.yaml"):
        self.config = ConfigManager(config_path)
        self.es_manager = ElasticsearchManager(self.config)
        self.gemini_client = GeminiClient(model_name="gemini-2.5-flash")
        self.relevance_gemini_client = GeminiClient(model_name="gemini-2.5-pro")
        self.langfuse_client = get_client()

        # Get Langfuse prompt for relevance evaluation
        self.relevance_prompt = self.langfuse_client.get_prompt("decide_whether_change_re-trigger_past_cause")
        self.relevance_schema = self.relevance_prompt.config["response_schema"]
        self.relevance_instruction = self.relevance_prompt.compile()

        # Attribute extraction prompt for change points
        self.attribute_extraction_prompt = self.langfuse_client.get_prompt("Extract attributes from query")
        self.attribute_extraction_schema = self.attribute_extraction_prompt.config["response_schema"]

        # Load unit list from config and prepare for attribute extraction
        self.unit_list = self.config.get("unit_list", [])
        unit_list_str = "\n".join(f"- {unit}" for unit in self.unit_list)
        self.attribute_extraction_instruction = self.attribute_extraction_prompt.compile(
            unit_list=unit_list_str
        )

        logger.info("RelevanceEvaluator initialized successfully")

    def get_aqos_record_by_doc_id(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve AQOS record from Elasticsearch by doc_id"""
        try:
            query = {"query": {"term": {"doc_id": doc_id}}}

            response = self.es_manager.search(query, size=1)
            hits = response.get("hits", {}).get("hits", [])

            if not hits:
                logger.warning(f"No AQOS record found for doc_id: {doc_id}")
                return None

            return hits[0]["_source"]

        except Exception as e:
            logger.error(f"Error retrieving AQOS record for doc_id {doc_id}: {e}")
            return None

    def extract_change_point_attributes(self, change_point: str, unit: str) -> Dict[str, str]:
        """Extract attributes from change point using Langfuse prompt and gemini-2.5-flash

        Args:
            change_point: The change point description
            unit: The unit field from CSV

        Returns:
            Dict with extracted attributes: {"unit": "", "part": "", "change": ""}

        """
        try:
            logger.debug(f"Extracting attributes for change_point: '{change_point[:50]}...', unit: '{unit}'")

            # Create user prompt as specified: "Part: {unit}\nQuery: {change_point}"
            user_prompt = f"Part: {unit}\nQuery: {change_point}"

            # Call Gemini API for attribute extraction
            result = self.gemini_client.generate_structured_content(
                prompt=user_prompt,
                response_schema=self.attribute_extraction_schema,
                system_instruction=self.attribute_extraction_instruction,
            )

            # Map response fields to required format
            extracted_attributes = {
                "unit": result.get("cause_unit", ""),
                "part": result.get("cause_part", ""),
                "change": result.get("unit_part_change", ""),
            }

            logger.debug(f"Extracted attributes: {extracted_attributes}")
            return extracted_attributes

        except Exception as e:
            logger.error(f"Error extracting change point attributes: {e}")
            # Return empty attributes on error
            return {"unit": "", "part": "", "change": ""}

    def evaluate_single_relevance(
        self, change_point: str, aqos_record: Dict[str, Any], unit: str = ""
    ) -> Tuple[bool, str]:
        """Evaluate relevance of a single change point and AQOS record pair using single-stage evaluation

        Returns:
            Tuple[bool, str]: (is_relevant, reasoning)

        """
        try:
            logger.debug("Starting relevance evaluation with attribute extraction")

            # Extract change point attributes using gemini-2.5-flash
            change_point_attributes = self.extract_change_point_attributes(change_point, unit)

            # Create structured prompt format for relevance evaluation
            relevance_prompt = json.dumps(
                {
                    "change_point": {
                        "unit": change_point_attributes["unit"],
                        "part": change_point_attributes["part"],
                        "change": change_point_attributes["change"],
                    },
                    "failure_record": {
                        "unit_part_change": aqos_record.get("cause", {}).get("part_change", "N/A")
                    },
                },
                ensure_ascii=False,
                indent=2,
            )

            logger.debug(f"Relevance evaluation prompt: {relevance_prompt}")

            # Generate relevance evaluation using Gemini client (gemini-2.5-pro)
            relevance_result = self.relevance_gemini_client.generate_structured_content(
                prompt=relevance_prompt,
                response_schema=self.relevance_schema,
                system_instruction=self.relevance_instruction,
            )

            is_relevant = relevance_result.get("is_relevant", False)
            reasoning = relevance_result.get("reasoning", "No reasoning provided")

            return is_relevant, reasoning

        except Exception as e:
            logger.error(f"Error in LLM evaluation: {e}")
            return False, f"Error: {str(e)}"

    def process_evaluation_row(self, row: pd.Series, index: int) -> Dict[str, Any]:
        """Process a single row from the evaluation CSV"""
        change_point = row["change_point"]
        defect_record_id = row["defect_record_id"]
        ground_truth = row["ground_truth"]
        unit = row["unit"]

        # Convert ground truth to boolean
        gt_bool = ground_truth == "TRUE" if isinstance(ground_truth, str) else bool(ground_truth)

        logger.info(
            f"Processing row {index}: change_point='{change_point[:50]}...', doc_id={defect_record_id}"
        )

        # Get AQOS record
        aqos_record = self.get_aqos_record_by_doc_id(defect_record_id)
        if aqos_record is None:
            label = generate_label(gt_bool, None)
            return {
                "index": index,
                "unit": unit,
                "change_point": change_point,
                "defect_record_id": defect_record_id,
                "unit_part_change": "N/A",
                "ground_truth": gt_bool,
                "prediction": None,
                "label": label,
                "reasoning": "AQOS record not found",
                "error": "missing_aqos_record",
            }

        # Evaluate relevance (now returns 2 values)
        prediction, reasoning = self.evaluate_single_relevance(change_point, aqos_record, unit)

        # Generate labels (TP/FP/TN/FN)
        label = generate_label(gt_bool, prediction)

        result = {
            "index": index,
            "unit": unit,
            "change_point": change_point,
            "defect_record_id": defect_record_id,
            "unit_part_change": aqos_record.get("cause", {}).get("part_change", "N/A")
            if aqos_record
            else "N/A",
            "ground_truth": gt_bool,
            "prediction": prediction,
            "label": label,
            "reasoning": reasoning,
            "error": None,
        }

        logger.debug(f"Row {index} result: GT={gt_bool}, Pred={prediction}")
        return result

    def evaluate_csv(self, csv_path: Path, max_workers: int = 4) -> List[Dict[str, Any]]:
        """Evaluate all rows in the CSV file"""
        logger.info(f"Loading evaluation data from: {csv_path}")
        df = pd.read_csv(csv_path)
        logger.info(f"Loaded {len(df)} evaluation records")

        results = []

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all evaluation tasks
            future_to_index = {}
            for index, row in df.iterrows():
                future = executor.submit(self.process_evaluation_row, row, index)
                future_to_index[future] = index

            # Collect results as they complete
            for future in as_completed(future_to_index):
                result = future.result()
                results.append(result)

        # Sort results by index to maintain original order
        results.sort(key=lambda x: x["index"])

        logger.info(f"Completed evaluation of {len(results)} records")
        return results

    def calculate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate precision, recall, and F1-score from evaluation results for relevance evaluation"""
        # Filter out results with errors
        valid_results = [r for r in results if r["error"] is None and r["prediction"] is not None]

        if not valid_results:
            logger.error("No valid results found for metric calculation")
            return {"error": "No valid results"}

        # === Relevance Evaluation Metrics ===
        y_true_relevance = [r["ground_truth"] for r in valid_results]
        y_pred_relevance = [r["prediction"] for r in valid_results]

        # Calculate relevance metrics
        precision_rel, recall_rel, f1_rel, support_rel = precision_recall_fscore_support(
            y_true_relevance, y_pred_relevance, average="binary", pos_label=True
        )

        # Calculate relevance confusion matrix
        cm_rel = confusion_matrix(y_true_relevance, y_pred_relevance)
        tn_rel, fp_rel, fn_rel, tp_rel = cm_rel.ravel()

        # === Per-unit metrics for relevance evaluation ===
        unit_metrics_relevance = {}
        units = set(r["unit"] for r in valid_results)

        for unit in units:
            unit_results = [r for r in valid_results if r["unit"] == unit]
            if unit_results:
                unit_y_true = [r["ground_truth"] for r in unit_results]
                unit_y_pred = [r["prediction"] for r in unit_results]

                if len(set(unit_y_true)) > 1:  # Only calculate if both classes present
                    unit_precision, unit_recall, unit_f1, _ = precision_recall_fscore_support(
                        unit_y_true, unit_y_pred, average="binary", pos_label=True
                    )
                    unit_metrics_relevance[unit] = {
                        "precision": float(unit_precision),
                        "recall": float(unit_recall),
                        "f1_score": float(unit_f1),
                        "count": len(unit_results),
                    }

        metrics = {
            "relevance_evaluation": {
                "overall": {
                    "precision": float(precision_rel),
                    "recall": float(recall_rel),
                    "f1_score": float(f1_rel),
                    "accuracy": float((tp_rel + tn_rel) / (tp_rel + tn_rel + fp_rel + fn_rel)),
                    "total_samples": len(valid_results),
                    "valid_samples": len(valid_results),
                    "error_samples": len(results) - len(valid_results),
                },
                "confusion_matrix": {
                    "true_negative": int(tn_rel),
                    "false_positive": int(fp_rel),
                    "false_negative": int(fn_rel),
                    "true_positive": int(tp_rel),
                },
                "by_unit": unit_metrics_relevance,
            },
        }

        return metrics

    def save_results(
        self, results: List[Dict[str, Any]], metrics: Dict[str, Any], output_dir: Path, timestamp_suffix: str
    ):
        """Save evaluation results and metrics to files with timestamp suffix"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save detailed results
        results_df = pd.DataFrame(results)
        results_path = output_dir / f"detailed_results_{timestamp_suffix}.csv"
        results_df.to_csv(results_path, index=False)
        logger.info(f"Detailed results saved to: {results_path}")

        # Save metrics
        metrics_path = output_dir / f"metrics_{timestamp_suffix}.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"Metrics saved to: {metrics_path}")

        # Save summary report
        summary_path = output_dir / f"summary_report_{timestamp_suffix}.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("Relevance Evaluation Accuracy Report\n")
            f.write("=" * 40 + "\n\n")

            if "error" not in metrics:
                # === Relevance Evaluation Results ===
                rel_overall = metrics["relevance_evaluation"]["overall"]
                f.write("RELEVANCE EVALUATION RESULTS:\n")
                f.write("-" * 30 + "\n")
                f.write("Overall Metrics:\n")
                f.write(f"  Precision: {rel_overall['precision']:.4f}\n")
                f.write(f"  Recall: {rel_overall['recall']:.4f}\n")
                f.write(f"  F1-Score: {rel_overall['f1_score']:.4f}\n")
                f.write(f"  Accuracy: {rel_overall['accuracy']:.4f}\n")
                f.write(f"  Total Samples: {rel_overall['total_samples']}\n")
                f.write(f"  Error Samples: {rel_overall['error_samples']}\n\n")

                rel_cm = metrics["relevance_evaluation"]["confusion_matrix"]
                f.write("Confusion Matrix:\n")
                f.write(f"  True Negative: {rel_cm['true_negative']}\n")
                f.write(f"  False Positive: {rel_cm['false_positive']}\n")
                f.write(f"  False Negative: {rel_cm['false_negative']}\n")
                f.write(f"  True Positive: {rel_cm['true_positive']}\n\n")

                if metrics["relevance_evaluation"]["by_unit"]:
                    f.write("Per-Unit Metrics:\n")
                    for unit, unit_metrics in metrics["relevance_evaluation"]["by_unit"].items():
                        f.write(f"  {unit}:\n")
                        f.write(f"    Precision: {unit_metrics['precision']:.4f}\n")
                        f.write(f"    Recall: {unit_metrics['recall']:.4f}\n")
                        f.write(f"    F1-Score: {unit_metrics['f1_score']:.4f}\n")
                        f.write(f"    Count: {unit_metrics['count']}\n")
            else:
                f.write(f"Error: {metrics['error']}\n")

        logger.info(f"Summary report saved to: {summary_path}")


@click.command()
@click.argument("csv_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default="evaluation_results",
    help="Output directory for results",
)
@click.option("--max-workers", type=int, default=4, help="Maximum number of parallel workers")
@click.option(
    "--config-path",
    type=click.Path(exists=True, path_type=Path),
    default="configs/6307204b.yaml",
    help="Configuration file path",
)
def main(csv_path: Path, output_dir: Path, max_workers: int, config_path: Path):
    """Evaluate relevance evaluation accuracy using ground truth CSV data"""
    logger.info("Starting relevance evaluation accuracy assessment")

    # Generate timestamp suffix
    timestamp_suffix = generate_timestamp_suffix()

    # Create timestamped output directory
    timestamped_output_dir = Path(f"{output_dir}_{timestamp_suffix}")

    logger.info(f"Results will be saved to: {timestamped_output_dir}")

    # Initialize evaluator
    evaluator = RelevanceEvaluator(str(config_path))

    # Run evaluation
    results = evaluator.evaluate_csv(csv_path, max_workers=max_workers)

    # Calculate metrics
    metrics = evaluator.calculate_metrics(results)

    # Save results
    evaluator.save_results(results, metrics, timestamped_output_dir, timestamp_suffix)

    # Print summary
    if "error" not in metrics:
        rel_overall = metrics["relevance_evaluation"]["overall"]
        logger.info("=" * 60)
        logger.info("RELEVANCE EVALUATION SUMMARY")
        logger.info("=" * 60)
        logger.info("RELEVANCE EVALUATION:")
        logger.info(f"  Precision: {rel_overall['precision']:.4f}")
        logger.info(f"  Recall: {rel_overall['recall']:.4f}")
        logger.info(f"  F1-Score: {rel_overall['f1_score']:.4f}")
        logger.info(f"  Accuracy: {rel_overall['accuracy']:.4f}")
        logger.info("-" * 30)
        logger.info(f"Total Samples: {rel_overall['total_samples']}")
        logger.info(f"Error Samples: {rel_overall['error_samples']}")
        logger.info("=" * 60)
    else:
        logger.error(f"Evaluation failed: {metrics['error']}")


if __name__ == "__main__":
    main()
