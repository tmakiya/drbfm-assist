"""DRBFM Purpose Workflow using LangGraph

This workflow searches past DRBFM records, failure reports, and design changes to draft failure modes,
causes, effects, and countermeasures for a given part and change point.

Workflow Steps:
1. Map part and change_point to section and function_category
2. DRBFM Search Flow:
   a. Full-text search on 'part' field with source_type="DRBFM" filter
   b. Vector search on 'change_point_embedding' field
   c. LLM filtering to select truly relevant documents
   d. LLM generation of failure modes based on input and reference documents
3. Failure Records Search Flow:
   a. Search failure records by section with source_type="品質会議提議内容詳細"
   b. Estimate failure modes from failure records using LLM
4. Design Change Search Flow:
   a. Search design changes by section and function_category with source_type="設計変更履歴"
   b. Estimate failure modes from design changes using LLM
5. Merge results from all three flows
"""

import json
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from typing import Any, Dict, List, Optional

from langgraph.graph import END, START, StateGraph
from langfuse import Langfuse
from loguru import logger
from pydantic import BaseModel, Field

from drassist.chains.base import BaseGraph, BaseGraphState
from drassist.elasticsearch.manager import ElasticsearchManager
from drassist.embeddings.azure_client import AzureOpenAIEmbedder
from drassist.llm.gemini_client import GeminiClient

# URL templates for source documents
DRBFM_URL_TEMPLATE = "https://caddi-drawer.com/1d84c619-4449-49e8-a5d2-92827a2d8580/documents/{source_id}?page=0&cateid=14b46f49-7691-408b-8e5d-ede0048987d2&documentPage=1"
FAILURE_REPORT_URL_TEMPLATE = "https://caddi-drawer.com/1d84c619-4449-49e8-a5d2-92827a2d8580?facetViewMode=true&focusOnLast=false&similarSearchFilter=&page=0&t=id&q={source_id}&filters="


def generate_source_url(source_type: str, source_id: str) -> str:
    """Generate URL for source document based on source_type"""
    if source_type == "DRBFM":
        return DRBFM_URL_TEMPLATE.format(source_id=source_id)
    elif source_type == "品質会議提議内容詳細":
        return FAILURE_REPORT_URL_TEMPLATE.format(source_id=source_id)
    elif source_type == "設計変更履歴":
        return DRBFM_URL_TEMPLATE.format(source_id=source_id)
    else:
        return ""


class Reference(BaseModel):
    """Reference to a source document (DRBFM or failure report)"""

    source_type: str = Field(default="DRBFM", description="Source type: DRBFM or 品質会議提議内容詳細")
    source_id: str = Field(..., description="Source document ID (original_file_id for DRBFM, drawing_id for failure reports)")
    source_URL: str = Field(default="", description="URL to the source document")
    source_section: str = Field(default="", description="Section from source document")
    source_part: str = Field(default="", description="Part name from source document")
    source_function_category: str = Field(default="", description="Function category from source document")
    source_function: str = Field(default="", description="Function from source document")
    source_change_point: str = Field(default="", description="Change point from source document")
    source_failure_mode: str = Field(default="", description="Failure mode from source")
    source_cause: str = Field(default="", description="Cause from source")
    source_effect: str = Field(default="", description="Effect from source")
    source_countermeasure: str = Field(default="", description="Countermeasure from source")


class GeneratedFailureMode(BaseModel):
    """Generated failure mode with references"""

    failure_mode: str = Field(..., description="Generated failure mode for the input part and change point")
    cause: str = Field(default="", description="Generated cause/factor")
    effect: str = Field(default="", description="Generated effect on customer")
    countermeasure: str = Field(default="", description="Generated recommended countermeasure")
    reasoning: str = Field(default="", description="Reasoning for this failure mode (from failure records estimation)")
    propriety: Optional[bool] = Field(default=None, description="Whether the failure mode is appropriate")
    propriety_reasoning: str = Field(default="", description="Reasoning for propriety judgment")
    references: List[Reference] = Field(
        default_factory=list, description="References to source documents used for generation"
    )


class DrbfmPurposeWorkflowState(BaseGraphState):
    """State for DRBFM Purpose workflow"""

    # Input
    part: str = Field(..., description="Input part name")
    change_point: str = Field(..., description="Input change point")

    # Mapped section and function_category from input
    input_section: str = Field(default="", description="Section mapped from input part and change_point")
    input_function_category: str = Field(default="", description="Function category mapped from input part and change_point")

    # Intermediate results - DRBFM search flow
    full_text_search_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from full-text search on part field (source_type=DRBFM)"
    )
    vector_search_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from vector search on change_point"
    )
    filtered_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results after LLM filtering"
    )
    drbfm_failure_modes: List[GeneratedFailureMode] = Field(
        default_factory=list, description="Failure modes generated from DRBFM records"
    )

    # Intermediate results - Failure records search flow
    failure_records_search_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from failure records search (source_type=品質会議提議内容詳細)"
    )
    failure_records_failure_modes: List[GeneratedFailureMode] = Field(
        default_factory=list, description="Failure modes estimated from failure records"
    )

    # Intermediate results - Design change search flow
    design_change_search_results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Results from design change search (source_type=設計変更履歴)"
    )
    design_change_failure_modes: List[GeneratedFailureMode] = Field(
        default_factory=list, description="Failure modes estimated from design changes"
    )

    # Intermediate - merged results before deduplication
    merged_failure_modes: List[GeneratedFailureMode] = Field(
        default_factory=list, description="Merged failure modes from all three flows (before deduplication)"
    )

    # Output - deduplicated results
    generated_failure_modes: List[GeneratedFailureMode] = Field(
        default_factory=list, description="Generated failure modes with references (after deduplication)"
    )


def map_part_to_section_and_function(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    langfuse_client: Langfuse,
) -> Dict[str, Any]:
    """Map input part and change_point to section and function_category using LLM"""
    logger.info(f"Mapping part '{state.part}' and change_point to section and function_category")

    try:
        # Get prompt and response_schema from Langfuse
        prompt_obj = langfuse_client.get_prompt("map_part_to_section_and_function")
        response_schema = prompt_obj.config["response_schema"]
        system_instruction = prompt_obj.compile()

        # Build the prompt
        prompt = json.dumps({
            "input_part": state.part,
            "input_part_change": state.change_point,
        }, ensure_ascii=False, indent=2)

        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        input_section = result.get("section", "")
        input_function_category = result.get("function", "")

        logger.info(f"Mapped to section='{input_section}', function_category='{input_function_category}'")
        return {
            "input_section": input_section,
            "input_function_category": input_function_category,
        }

    except Exception as e:
        logger.error(f"Failed to map part to section and function: {e}")
        return {
            "input_section": "",
            "input_function_category": "",
        }


def execute_full_text_search(
    state: DrbfmPurposeWorkflowState,
    es_manager: ElasticsearchManager,
    search_size: int = 100,
) -> Dict[str, Any]:
    """Execute full-text search on part field with source_type=DRBFM filter"""
    logger.info(f"Executing full-text search for part: {state.part} (source_type=DRBFM)")

    # Build match query for part field with source_type filter
    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "match": {
                            "part": {
                                "query": state.part,
                                "operator": "or",
                            }
                        }
                    }
                ],
                "filter": [
                    {
                        "term": {
                            "source_type": "DRBFM"
                        }
                    }
                ]
            }
        },
        "_source": [
            "doc_id", "source_id", "source_type", "section", "function_category",
            "part", "function", "change_point", "failure_mode", "cause", "effect", "countermeasure"
        ],
    }

    try:
        response = es_manager.search(query, size=search_size)
        hits = response.get("hits", {}).get("hits", [])

        results = []
        for hit in hits:
            source = hit["_source"]
            results.append({
                "doc_id": source.get("doc_id"),
                "source_id": str(source.get("source_id", "")),
                "source_type": source.get("source_type", "DRBFM"),
                "section": source.get("section", ""),
                "function_category": source.get("function_category", ""),
                "part": source.get("part", ""),
                "function": source.get("function", ""),
                "change_point": source.get("change_point", ""),
                "failure_mode": source.get("failure_mode", ""),
                "cause": source.get("cause", ""),
                "effect": source.get("effect", ""),
                "countermeasure": source.get("countermeasure", ""),
                "score": hit["_score"],
            })

        logger.info(f"Full-text search found {len(results)} DRBFM results")
        return {"full_text_search_results": results}

    except Exception as e:
        logger.error(f"Full-text search failed: {e}")
        return {"full_text_search_results": []}


def execute_vector_search(
    state: DrbfmPurposeWorkflowState,
    es_manager: ElasticsearchManager,
    embedder: AzureOpenAIEmbedder,
    search_size: int = 20,
) -> Dict[str, Any]:
    """Execute vector search on change_point_embedding field with source_type=DRBFM filter"""
    logger.info(f"Executing vector search for change_point: {state.change_point[:50]}...")

    if not state.full_text_search_results:
        logger.warning("No full-text search results to filter with vector search")
        return {"vector_search_results": []}

    # Get doc_ids from full-text search results
    doc_ids = [r["doc_id"] for r in state.full_text_search_results if r.get("doc_id") is not None]

    if not doc_ids:
        logger.warning("No valid doc_ids from full-text search")
        return {"vector_search_results": []}

    # Generate embedding for input change_point
    query_embedding = embedder.generate_embedding(state.change_point)
    if query_embedding is None:
        logger.error("Failed to generate embedding for change_point")
        return {"vector_search_results": []}

    # Build KNN query with filter for doc_ids from step 1 and source_type=DRBFM
    query = {
        "knn": {
            "field": "change_point_embedding",
            "query_vector": query_embedding,
            "k": min(search_size, len(doc_ids)),
            "num_candidates": max(search_size * 10, 100),
            "filter": {
                "bool": {
                    "must": [
                        {"terms": {"doc_id": doc_ids}},
                        {"term": {"source_type": "DRBFM"}}
                    ]
                }
            }
        },
        "_source": [
            "doc_id", "source_id", "source_type", "section", "function_category",
            "part", "function", "change_point", "failure_mode", "cause", "effect", "countermeasure"
        ],
    }

    try:
        response = es_manager.search(query, size=search_size)
        hits = response.get("hits", {}).get("hits", [])

        # Build lookup from full_text_search_results for additional fields
        full_text_lookup = {r["doc_id"]: r for r in state.full_text_search_results}

        results = []
        for hit in hits:
            source = hit["_source"]
            doc_id = source.get("doc_id")
            # Get additional fields from full-text search results if available
            full_text_doc = full_text_lookup.get(doc_id, {})
            results.append({
                "doc_id": doc_id,
                "source_id": str(source.get("source_id", full_text_doc.get("source_id", ""))),
                "source_type": source.get("source_type", full_text_doc.get("source_type", "DRBFM")),
                "section": source.get("section", full_text_doc.get("section", "")),
                "function_category": source.get("function_category", full_text_doc.get("function_category", "")),
                "part": source.get("part", ""),
                "function": source.get("function", ""),
                "change_point": source.get("change_point", ""),
                "failure_mode": source.get("failure_mode", ""),
                "cause": source.get("cause", ""),
                "effect": source.get("effect", ""),
                "countermeasure": source.get("countermeasure", ""),
                "score": hit["_score"],
            })

        logger.info(f"Vector search found {len(results)} DRBFM results")
        return {"vector_search_results": results}

    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"vector_search_results": []}


def search_failure_records(
    state: DrbfmPurposeWorkflowState,
    es_manager: ElasticsearchManager,
    search_size: int = 100,
) -> Dict[str, Any]:
    """Search failure records by section and function_category with source_type=品質会議提議内容詳細"""
    logger.info(f"Searching failure records for section: {state.input_section}, function_category: {state.input_function_category}")

    if not state.input_section or not state.input_function_category:
        logger.warning("No input_section or input_function_category available, skipping failure records search")
        return {"failure_records_search_results": []}

    # Build query for failure records matching section and function_category
    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "section": state.input_section
                        }
                    },
                    {
                        "term": {
                            "function_category": state.input_function_category
                        }
                    }
                ],
                "filter": [
                    {
                        "term": {
                            "source_type": "品質会議提議内容詳細"
                        }
                    }
                ]
            }
        },
        "_source": [
            "doc_id", "source_id", "source_type", "section", "function_category",
            "function", "failure_mode"
        ],
    }

    try:
        response = es_manager.search(query, size=search_size)
        hits = response.get("hits", {}).get("hits", [])

        results = []
        for hit in hits:
            source = hit["_source"]
            results.append({
                "doc_id": source.get("doc_id"),
                "source_id": str(source.get("source_id", "")),
                "source_type": source.get("source_type", "品質会議提議内容詳細"),
                "section": source.get("section", ""),
                "function_category": source.get("function_category", ""),
                "function": source.get("function", ""),
                "failure_mode": source.get("failure_mode", ""),
                "score": hit.get("_score", 0),
            })

        logger.info(f"Failure records search found {len(results)} results")
        return {"failure_records_search_results": results}

    except Exception as e:
        logger.error(f"Failure records search failed: {e}")
        return {"failure_records_search_results": []}


def estimate_failure_from_failure_records(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    langfuse_client: Langfuse,
) -> Dict[str, Any]:
    """Estimate failure modes from failure records using LLM"""
    logger.info("Estimating failure modes from failure records")

    if not state.failure_records_search_results:
        logger.warning("No failure records to estimate from")
        return {"failure_records_failure_modes": []}

    try:
        # Get prompt and response_schema from Langfuse
        prompt_obj = langfuse_client.get_prompt("estimate_failure_from_failure_records")
        response_schema = prompt_obj.config["response_schema"]
        system_instruction = prompt_obj.compile()

        # Prepare failure records for the prompt
        failure_records = []
        for record in state.failure_records_search_results:
            failure_records.append({
                "source_id": record["source_id"],
                "section": record["section"],
                "function": record.get("function", ""),
                "failure_mode": record.get("failure_mode", ""),
            })

        # Build the prompt
        prompt = json.dumps({
            "DRBFM_row": {
                "part": state.part,
                "change_point": state.change_point,
            },
            "failure_records": failure_records,
        }, ensure_ascii=False, indent=2)

        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Build lookup for failure records
        record_lookup = {r["source_id"]: r for r in state.failure_records_search_results}

        # Convert result to GeneratedFailureMode objects
        failure_modes = []
        for idx, row in enumerate(result["estimated_failures"]):
            # Build references from source_ids
            references = []
            for source_id in row.get("source_ids", []):
                if source_id in record_lookup:
                    record = record_lookup[source_id]
                    source_type = record.get("source_type", "品質会議提議内容詳細")
                    references.append(Reference(
                        source_type=source_type,
                        source_id=source_id,
                        source_URL=generate_source_url(source_type, source_id),
                        source_section=record.get("section", ""),
                        source_part="",
                        source_function_category=record.get("function_category", ""),
                        source_function=record.get("function", ""),
                        source_change_point="",
                        source_failure_mode=record.get("failure_mode", ""),
                        source_cause="",
                        source_effect="",
                        source_countermeasure="",
                    ))

            failure_modes.append(GeneratedFailureMode(
                failure_mode=row.get("failure_mode", ""),
                cause=row.get("cause", ""),
                effect=row.get("effect", ""),
                countermeasure=row.get("countermeasure", ""),
                reasoning=row.get("reasoning", ""),
                references=references,
            ))

        logger.info(f"Estimated {len(failure_modes)} failure modes from failure records")
        return {"failure_records_failure_modes": failure_modes}

    except Exception as e:
        logger.error(f"Failed to estimate failure modes from failure records: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return {"failure_records_failure_modes": []}


def _evaluate_single_document(
    doc: Dict[str, Any],
    input_part: str,
    input_change_point: str,
    gemini_client,
    system_instruction: str,
    response_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate a single document for relevance"""
    prompt = json.dumps({
        "input": {
            "part": input_part,
            "change_point": input_change_point,
        },
        "candidate": {
            "doc_id": doc["doc_id"],
            "part": doc["part"],
            "change_point": doc["change_point"],
        }
    }, ensure_ascii=False, indent=2)

    try:
        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )
        return {
            "doc_id": doc["doc_id"],
            "is_relevant": result.get("is_relevant", False),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        logger.error(f"Failed to evaluate document {doc['doc_id']}: {e}")
        return {
            "doc_id": doc["doc_id"],
            "is_relevant": False,
            "reasoning": f"Evaluation failed: {e}",
        }


def filter_with_llm(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    top_k: int = 10,
) -> Dict[str, Any]:
    """Step 3: Filter search results using LLM to select truly relevant documents"""
    logger.info(f"Filtering top {top_k} results with LLM")

    if not state.vector_search_results:
        logger.warning("No vector search results to filter")
        return {"filtered_results": []}

    # Take top_k results for LLM evaluation
    candidates = state.vector_search_results[:top_k]

    # System instruction for relevance evaluation
    system_instruction = """あなたは過去のDRBFM（Design Review Based on Failure Mode）記録の関連性を評価する専門家です。

入力された「部品」と「変更点」に対して、候補となる過去DRBFM記録が本当に関連しているかを判定してください。

判定基準:
1. 部品が同一または類似しているか
2. 変更点の内容が同義または類似しているか
3. 過去の記録が今回の変更に対するリスク評価の参考になるか

関連性があると判断する場合:
- 部品名が完全一致または部分一致している
- 変更点の技術的な内容が類似している
- 過去の故障モードや対策が今回の変更に適用可能

関連性がないと判断する場合:
- 部品が全く異なる
- 変更点の内容が技術的に無関係
- 過去の記録が今回の変更に参考にならない"""

    response_schema = {
        "type": "object",
        "properties": {
            "is_relevant": {
                "type": "boolean",
                "description": "Whether the candidate document is relevant to the input"
            },
            "reasoning": {
                "type": "string",
                "description": "Reasoning for the relevance decision"
            }
        },
        "required": ["is_relevant", "reasoning"]
    }

    # Evaluate candidates in parallel
    evaluation_results = []
    max_workers = min(8, len(candidates))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for doc in candidates:
            future = executor.submit(
                _evaluate_single_document,
                doc,
                state.part,
                state.change_point,
                gemini_client,
                system_instruction,
                response_schema,
            )
            futures[future] = doc

        for future in as_completed(futures):
            result = future.result()
            evaluation_results.append(result)

    # Filter to keep only relevant documents
    relevant_doc_ids = {r["doc_id"] for r in evaluation_results if r["is_relevant"]}
    filtered_results = [doc for doc in candidates if doc["doc_id"] in relevant_doc_ids]

    logger.info(f"LLM filtering: {len(filtered_results)}/{len(candidates)} documents deemed relevant")

    return {"filtered_results": filtered_results}


def generate_failure_modes(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    langfuse_client: Langfuse,
) -> Dict[str, Any]:
    """Generate failure modes from DRBFM records using LLM.

    Uses the 'estimate_failure_from_drbfm' prompt from Langfuse to generate
    failure modes based on filtered DRBFM reference documents.
    """
    logger.info("Generating failure modes from DRBFM records")

    if not state.filtered_results:
        logger.warning("No filtered results to generate failure modes from")
        return {"drbfm_failure_modes": []}

    try:
        # Get prompt and response_schema from Langfuse
        prompt_obj = langfuse_client.get_prompt("estimate_failure_from_drbfm")
        response_schema = prompt_obj.config["response_schema"]
        system_instruction = prompt_obj.compile()

        # Prepare reference documents for the prompt (include doc_id for unique identification)
        reference_docs = []
        for doc in state.filtered_results:
            reference_docs.append({
                "doc_id": str(doc.get("doc_id", "")),
                "source_id": doc.get("source_id", ""),
                "source_type": doc.get("source_type", "DRBFM"),
                "section": doc.get("section", ""),
                "function_category": doc.get("function_category", ""),
                "part": doc["part"],
                "function": doc.get("function", ""),
                "change_point": doc["change_point"],
                "failure_mode": doc.get("failure_mode", ""),
                "cause": doc.get("cause", ""),
                "effect": doc.get("effect", ""),
                "countermeasure": doc.get("countermeasure", ""),
            })

        # Build the prompt
        prompt = json.dumps({
            "DRBFM_row": {
                "part": state.part,
                "change_point": state.change_point,
            },
            "drbfm_records": reference_docs,
        }, ensure_ascii=False, indent=2)

        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Build a lookup map for reference documents by doc_id (unique identifier)
        doc_lookup = {doc["doc_id"]: doc for doc in reference_docs}

        # Convert result to GeneratedFailureMode objects
        # Result is expected to be a list of failure mode objects
        generated_failure_modes = []
        for row in result["estimated_failures"]:
            # Build references from doc_ids
            references = []
            for doc_id in row.get("doc_ids", []):
                if doc_id in doc_lookup:
                    doc = doc_lookup[doc_id]
                    source_type = doc.get("source_type", "DRBFM")
                    source_id = doc.get("source_id", "")
                    references.append(Reference(
                        source_type=source_type,
                        source_id=source_id,
                        source_URL=generate_source_url(source_type, source_id),
                        source_section=doc.get("section", ""),
                        source_part=doc["part"],
                        source_function_category=doc.get("function_category", ""),
                        source_function=doc.get("function", ""),
                        source_change_point=doc["change_point"],
                        source_failure_mode=doc.get("failure_mode", ""),
                        source_cause=doc.get("cause", ""),
                        source_effect=doc.get("effect", ""),
                        source_countermeasure=doc.get("countermeasure", ""),
                    ))

            generated_failure_modes.append(GeneratedFailureMode(
                failure_mode=row.get("failure_mode", ""),
                cause=row.get("cause", ""),
                effect=row.get("effect", ""),
                countermeasure=row.get("countermeasure", ""),
                reasoning=row.get("reasoning", ""),
                references=references,
            ))

        logger.info(f"Generated {len(generated_failure_modes)} failure modes from DRBFM records")
        return {"drbfm_failure_modes": generated_failure_modes}

    except Exception as e:
        logger.error(f"Failed to generate failure modes: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return {"drbfm_failure_modes": []}


def search_design_changes(
    state: DrbfmPurposeWorkflowState,
    es_manager: ElasticsearchManager,
    search_size: int = 100,
) -> Dict[str, Any]:
    """Search design changes by section and function_category with source_type=設計変更履歴"""
    logger.info(f"Searching design changes for section: {state.input_section}, function_category: {state.input_function_category}")

    if not state.input_section or not state.input_function_category:
        logger.warning("No input_section or input_function_category available, skipping design change search")
        return {"design_change_search_results": []}

    # Build query for design changes matching section and function_category
    query = {
        "query": {
            "bool": {
                "must": [
                    {
                        "term": {
                            "section": state.input_section
                        }
                    },
                    {
                        "term": {
                            "function_category": state.input_function_category
                        }
                    }
                ],
                "filter": [
                    {
                        "term": {
                            "source_type": "設計変更履歴"
                        }
                    }
                ]
            }
        },
        "_source": [
            "doc_id", "source_id", "source_type", "section", "function_category",
            "function", "failure_mode", "product"
        ],
    }

    try:
        response = es_manager.search(query, size=search_size)
        hits = response.get("hits", {}).get("hits", [])

        results = []
        for hit in hits:
            source = hit["_source"]
            results.append({
                "doc_id": source.get("doc_id"),
                "source_id": str(source.get("source_id", "")),
                "source_type": source.get("source_type", "設計変更履歴"),
                "section": source.get("section", ""),
                "function_category": source.get("function_category", ""),
                "function": source.get("function", ""),
                "failure_mode": source.get("failure_mode", ""),
                "product": source.get("product", ""),
                "score": hit.get("_score", 0),
            })

        logger.info(f"Design change search found {len(results)} results")
        return {"design_change_search_results": results}

    except Exception as e:
        logger.error(f"Design change search failed: {e}")
        return {"design_change_search_results": []}


def estimate_failure_from_design_changes(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    langfuse_client: Langfuse,
) -> Dict[str, Any]:
    """Estimate failure modes from design changes using LLM"""
    logger.info("Estimating failure modes from design changes")

    if not state.design_change_search_results:
        logger.warning("No design changes to estimate from")
        return {"design_change_failure_modes": []}

    try:
        # Get prompt and response_schema from Langfuse (reuse the same prompt as failure records)
        prompt_obj = langfuse_client.get_prompt("estimate_failure_from_failure_records", label="1d84c619")
        response_schema = prompt_obj.config["response_schema"]
        system_instruction = prompt_obj.compile()

        # Prepare design change records for the prompt (using same schema as failure_records)
        failure_records = []
        for record in state.design_change_search_results:
            failure_records.append({
                "source_id": record["source_id"],
                "section": record["section"],
                "function": record.get("function", ""),
                "failure_mode": record.get("failure_mode", ""),
            })

        # Build the prompt
        prompt = json.dumps({
            "DRBFM_row": {
                "part": state.part,
                "change_point": state.change_point,
            },
            "failure_records": failure_records,
        }, ensure_ascii=False, indent=2)

        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Build lookup for design change records
        record_lookup = {r["source_id"]: r for r in state.design_change_search_results}

        # Convert result to GeneratedFailureMode objects
        failure_modes = []
        for idx, row in enumerate(result["estimated_failures"]):
            # Build references from source_ids
            references = []
            for source_id in row.get("source_ids", []):
                if source_id in record_lookup:
                    record = record_lookup[source_id]
                    source_type = "設計変更履歴"  # Always use 設計変更履歴 for design changes
                    references.append(Reference(
                        source_type=source_type,
                        source_id=source_id,
                        source_URL=generate_source_url(source_type, source_id),
                        source_section=record.get("section", ""),
                        source_part="",
                        source_function_category=record.get("function_category", ""),
                        source_function=record.get("function", ""),
                        source_change_point="",
                        source_failure_mode=record.get("failure_mode", ""),
                        source_cause="",
                        source_effect="",
                        source_countermeasure="",
                    ))

            failure_modes.append(GeneratedFailureMode(
                failure_mode=row.get("failure_mode", ""),
                cause=row.get("cause", ""),
                effect=row.get("effect", ""),
                countermeasure=row.get("countermeasure", ""),
                reasoning=row.get("reasoning", ""),
                references=references,
            ))

        logger.info(f"Estimated {len(failure_modes)} failure modes from design changes")
        return {"design_change_failure_modes": failure_modes}

    except Exception as e:
        logger.error(f"Failed to estimate failure modes from design changes: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return {"design_change_failure_modes": []}


def merge_results(
    state: DrbfmPurposeWorkflowState,
) -> Dict[str, Any]:
    """Merge failure modes from DRBFM, failure records, and design change flows"""
    logger.info("Merging failure modes from DRBFM, failure records, and design change flows")

    # Combine failure modes from all three flows
    merged = []
    merged.extend(state.drbfm_failure_modes)
    merged.extend(state.failure_records_failure_modes)
    merged.extend(state.design_change_failure_modes)

    logger.info(
        f"Merged {len(state.drbfm_failure_modes)} DRBFM failure modes + "
        f"{len(state.failure_records_failure_modes)} failure records failure modes + "
        f"{len(state.design_change_failure_modes)} design change failure modes = "
        f"{len(merged)} total"
    )

    return {"merged_failure_modes": merged}


def deduplicate_failure_modes(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
) -> Dict[str, Any]:
    """Deduplicate failure modes by merging those with equivalent failure_mode and cause"""
    logger.info("Deduplicating failure modes with equivalent failure_mode and cause")

    if not state.merged_failure_modes:
        logger.warning("No failure modes to deduplicate")
        return {"generated_failure_modes": []}

    if len(state.merged_failure_modes) == 1:
        logger.info("Only one failure mode, no deduplication needed")
        return {"generated_failure_modes": state.merged_failure_modes}

    try:
        # Prepare failure modes with indices for LLM
        indexed_failure_modes = []
        for idx, fm in enumerate(state.merged_failure_modes):
            indexed_failure_modes.append({
                "index": idx,
                "failure_mode": fm.failure_mode,
                "cause": fm.cause,
                "effect": fm.effect,
                "countermeasure": fm.countermeasure,
                "reasoning": fm.reasoning,
            })

        # System instruction for deduplication
        system_instruction = """あなたは故障モード分析の専門家です。

以下の故障モードリストから、failure_mode（故障モード）とcause（原因）が内容的に同等のものをグループ化してください。

## 判定基準
- failure_modeが同じ現象を指している
- causeが同じ原因を指している
- 両方が同等の場合のみ、同じグループとして集約

## 出力ルール
1. failure_mode, cause, reasoning: 同等の内容を1つの文に統合
2. effect, countermeasure: 
   - 内容が同等の場合: 1つの文に統合
   - 内容が異なる場合: ","区切りで連結（例: "効果A, 効果B"）
3. source_indices: 集約元のインデックスをリストで返す

## 注意
- 集約されないものは単独のグループとして出力
- 全てのインデックスが必ずいずれかのグループに含まれること
- source_indicesは必ず元のインデックス番号を正確に返すこと"""

        response_schema = {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "merged_failure_mode": {"type": "string", "description": "統合された故障モード"},
                            "merged_cause": {"type": "string", "description": "統合された原因"},
                            "merged_effect": {"type": "string", "description": "統合された影響（異なる場合は,区切り）"},
                            "merged_countermeasure": {"type": "string", "description": "統合された対策（異なる場合は,区切り）"},
                            "merged_reasoning": {"type": "string", "description": "統合された推論"},
                            "source_indices": {"type": "array", "items": {"type": "integer"}, "description": "集約元のインデックス"}
                        },
                        "required": ["merged_failure_mode", "merged_cause", "merged_effect", 
                                    "merged_countermeasure", "merged_reasoning", "source_indices"]
                    }
                }
            },
            "required": ["groups"]
        }

        # Build the prompt
        prompt = json.dumps({
            "failure_modes": indexed_failure_modes,
        }, ensure_ascii=False, indent=2)

        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )

        # Build deduplicated failure modes using source_indices for references
        deduplicated_failure_modes = []
        for group in result.get("groups", []):
            # Collect references from all source indices
            merged_references = []
            for idx in group.get("source_indices", []):
                if 0 <= idx < len(state.merged_failure_modes):
                    merged_references.extend(state.merged_failure_modes[idx].references)

            deduplicated_failure_modes.append(GeneratedFailureMode(
                failure_mode=group.get("merged_failure_mode", ""),
                cause=group.get("merged_cause", ""),
                effect=group.get("merged_effect", ""),
                countermeasure=group.get("merged_countermeasure", ""),
                reasoning=group.get("merged_reasoning", ""),
                references=merged_references,
            ))

        logger.info(f"Deduplicated {len(state.merged_failure_modes)} failure modes to {len(deduplicated_failure_modes)}")
        return {"generated_failure_modes": deduplicated_failure_modes}

    except Exception as e:
        logger.error(f"Failed to deduplicate failure modes: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        # Return original failure modes without deduplication
        return {"generated_failure_modes": state.merged_failure_modes}


def _reflect_single_failure_mode(
    fm: GeneratedFailureMode,
    input_part: str,
    input_change_point: str,
    gemini_client,
    system_instruction: str,
    response_schema: Dict[str, Any],
) -> Dict[str, Any]:
    """Reflect on a single failure mode to evaluate propriety"""
    prompt = json.dumps({
        "input_part": input_part,
        "input_change_point": input_change_point,
        "failure_mode": fm.failure_mode,
        "reasoning": fm.reasoning,
    }, ensure_ascii=False, indent=2)

    try:
        result = gemini_client.generate_structured_content(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )
        return {
            "failure_mode": fm.failure_mode,
            "propriety": result.get("propriety", None),
            "propriety_reasoning": result.get("propriety_reasoning", ""),
        }
    except Exception as e:
        # Log detailed error information
        error_type = type(e).__name__
        logger.error(f"Failed to reflect on failure mode '{fm.failure_mode[:30]}...': {error_type}: {e}")
        
        # Log cause if available (for chained exceptions like RetryError)
        if hasattr(e, '__cause__') and e.__cause__:
            cause_type = type(e.__cause__).__name__
            logger.error(f"  Cause: {cause_type}: {e.__cause__}")
        
        # Log args for more details
        if hasattr(e, 'args') and e.args:
            logger.error(f"  Args: {e.args}")
        
        # Log full traceback for debugging
        logger.error(f"  Traceback:\n{traceback.format_exc()}")
        
        return {
            "failure_mode": fm.failure_mode,
            "propriety": None,
            "propriety_reasoning": f"Reflection failed: {error_type}: {e}",
        }


def reflect_generated_failure_modes(
    state: DrbfmPurposeWorkflowState,
    gemini_client,
    langfuse_client: Langfuse,
) -> Dict[str, Any]:
    """Reflect on generated failure modes to evaluate propriety using LLM"""
    logger.info("Reflecting on generated failure modes to evaluate propriety")

    if not state.generated_failure_modes:
        logger.warning("No generated failure modes to reflect on")
        return {"generated_failure_modes": []}

    try:
        # Get prompt and response_schema from Langfuse
        prompt_obj = langfuse_client.get_prompt("reflect_generated_failure_mode")
        response_schema = prompt_obj.config["response_schema"]
        system_instruction = prompt_obj.compile()

        # Evaluate each failure mode in parallel
        reflection_results = []
        max_workers = min(8, len(state.generated_failure_modes))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for fm in state.generated_failure_modes:
                future = executor.submit(
                    _reflect_single_failure_mode,
                    fm,
                    state.part,
                    state.change_point,
                    gemini_client,
                    system_instruction,
                    response_schema,
                )
                futures[future] = fm

            for future in as_completed(futures):
                result = future.result()
                reflection_results.append(result)

        # Build lookup for reflection results
        reflection_lookup = {r["failure_mode"]: r for r in reflection_results}

        # Update failure modes with propriety information
        updated_failure_modes = []
        for fm in state.generated_failure_modes:
            reflection = reflection_lookup.get(fm.failure_mode, {})
            updated_fm = GeneratedFailureMode(
                failure_mode=fm.failure_mode,
                cause=fm.cause,
                effect=fm.effect,
                countermeasure=fm.countermeasure,
                reasoning=fm.reasoning,
                propriety=reflection.get("propriety"),
                propriety_reasoning=reflection.get("propriety_reasoning", ""),
                references=fm.references,
            )
            updated_failure_modes.append(updated_fm)

        logger.info(f"Reflected on {len(updated_failure_modes)} failure modes")
        return {"generated_failure_modes": updated_failure_modes}

    except Exception as e:
        logger.error(f"Failed to reflect on failure modes: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        # Return original failure modes without propriety information
        return {"generated_failure_modes": state.generated_failure_modes}


class DrbfmPurposeWorkflow(BaseGraph):
    """DRBFM Purpose Workflow for drafting failure modes from past records and failure reports"""

    def __init__(
        self,
        config_path: str = "configs/drbfm_purpose.yaml",
        gemini_model_name: str = "gemini-2.5-pro",
        reflection_model_name: str = "gemini-2.5-pro",
    ):
        super().__init__(config_path, gemini_model_name)
        self._embedder = None
        self._langfuse_client = None
        self._reflection_gemini_client = None
        self._reflection_model_name = reflection_model_name

    @property
    def state_class(self) -> type[BaseGraphState]:
        return DrbfmPurposeWorkflowState

    @property
    def embedder(self) -> AzureOpenAIEmbedder:
        if self._embedder is None:
            self._embedder = AzureOpenAIEmbedder(self.config_manager)
        return self._embedder

    @property
    def langfuse_client(self) -> Langfuse:
        if self._langfuse_client is None:
            self._langfuse_client = Langfuse()
        return self._langfuse_client

    @property
    def reflection_gemini_client(self) -> GeminiClient:
        """Gemini client for reflection/propriety evaluation using gemini-2.5-pro"""
        if self._reflection_gemini_client is None:
            self._reflection_gemini_client = GeminiClient(
                model_name=self._reflection_model_name,
            )
        return self._reflection_gemini_client

    def create_workflow(self) -> StateGraph:
        """Create the DRBFM Purpose workflow graph

        Workflow structure:
        START
          ↓
        map_part_to_section_and_function
          ↓
        ┌─────────────────────────────────────────────────┐
        │ Parallel execution (3 flows)                     │
        │ ├─ DRBFM search flow                            │
        │ │   ├─ full_text_search                         │
        │ │   ├─ vector_search                            │
        │ │   ├─ llm_filter                               │
        │ │   └─ generate_failure_modes                   │
        │ │                                               │
        │ ├─ Failure records search flow                  │
        │ │   ├─ search_failure_records                   │
        │ │   └─ estimate_failure_from_failure_records    │
        │ │                                               │
        │ └─ Design change search flow                    │
        │     ├─ search_design_changes                    │
        │     └─ estimate_failure_from_design_changes     │
        └─────────────────────────────────────────────────┘
          ↓
        merge_results
          ↓
        END
        """
        workflow = StateGraph(DrbfmPurposeWorkflowState)

        # Get search parameters from config
        vector_search_size = self.config_manager.get("search.vector_search_size", 20)
        llm_filter_top_k = self.config_manager.get("search.llm_filter_top_k", 10)

        # Add nodes - Step 1: Map part to section and function
        workflow.add_node(
            "map_part_to_section_and_function",
            partial(
                map_part_to_section_and_function,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Add nodes - DRBFM search flow
        workflow.add_node(
            "full_text_search",
            partial(
                execute_full_text_search,
                es_manager=self.es_manager,
                search_size=100,
            ),
        )

        workflow.add_node(
            "vector_search",
            partial(
                execute_vector_search,
                es_manager=self.es_manager,
                embedder=self.embedder,
                search_size=vector_search_size,
            ),
        )

        workflow.add_node(
            "llm_filter",
            partial(
                filter_with_llm,
                gemini_client=self.gemini_client,
                top_k=llm_filter_top_k,
            ),
        )

        workflow.add_node(
            "generate_failure_modes",
            partial(
                generate_failure_modes,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Add nodes - Failure records search flow
        workflow.add_node(
            "search_failure_records",
            partial(
                search_failure_records,
                es_manager=self.es_manager,
                search_size=100,
            ),
        )

        workflow.add_node(
            "estimate_failure_from_failure_records",
            partial(
                estimate_failure_from_failure_records,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Add nodes - Design change search flow
        workflow.add_node(
            "search_design_changes",
            partial(
                search_design_changes,
                es_manager=self.es_manager,
                search_size=100,
            ),
        )

        workflow.add_node(
            "estimate_failure_from_design_changes",
            partial(
                estimate_failure_from_design_changes,
                gemini_client=self.gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Add nodes - Merge results
        workflow.add_node("merge_results", merge_results)

        # Add nodes - Deduplicate failure modes
        workflow.add_node(
            "deduplicate_failure_modes",
            partial(
                deduplicate_failure_modes,
                gemini_client=self.gemini_client,
            ),
        )

        # Add nodes - Reflect on generated failure modes (using gemini-2.5-pro)
        workflow.add_node(
            "reflect_generated_failure_modes",
            partial(
                reflect_generated_failure_modes,
                gemini_client=self.reflection_gemini_client,
                langfuse_client=self.langfuse_client,
            ),
        )

        # Define edges
        # Start with mapping
        workflow.add_edge(START, "map_part_to_section_and_function")

        # After mapping, run all three flows in parallel
        # DRBFM flow
        workflow.add_edge("map_part_to_section_and_function", "full_text_search")
        workflow.add_edge("full_text_search", "vector_search")
        workflow.add_edge("vector_search", "llm_filter")
        workflow.add_edge("llm_filter", "generate_failure_modes")

        # Failure records flow (runs after mapping)
        workflow.add_edge("map_part_to_section_and_function", "search_failure_records")
        workflow.add_edge("search_failure_records", "estimate_failure_from_failure_records")

        # Design change flow (runs after mapping)
        workflow.add_edge("map_part_to_section_and_function", "search_design_changes")
        workflow.add_edge("search_design_changes", "estimate_failure_from_design_changes")

        # All three flows merge at merge_results
        workflow.add_edge("generate_failure_modes", "merge_results")
        workflow.add_edge("estimate_failure_from_failure_records", "merge_results")
        workflow.add_edge("estimate_failure_from_design_changes", "merge_results")

        # Deduplicate failure modes
        workflow.add_edge("merge_results", "deduplicate_failure_modes")

        # Reflect on generated failure modes
        workflow.add_edge("deduplicate_failure_modes", "reflect_generated_failure_modes")

        # End
        workflow.add_edge("reflect_generated_failure_modes", END)

        return workflow
