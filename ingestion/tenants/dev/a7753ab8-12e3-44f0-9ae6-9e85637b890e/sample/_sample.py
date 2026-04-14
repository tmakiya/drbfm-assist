"""Sample script for Gemini image analysis without Langfuse.

This script demonstrates the complete pipeline:
1. Query MSQP for drawing_id and file_path
2. Download images from GCS
3. Analyze images with Gemini (direct usage, no Langfuse)
4. Index analysis results to ISP

Prerequisites:
- .env file must contain valid credentials (TENANT_ID, MSQP_CLIENT_ID, MSQP_CLIENT_SECRET, ENV)
- For LOCAL_MODE=true: Run setup_local_proxy.sh to start SOCKS5 proxy and kubectl port-forward

Usage:
    # 1. Setup local proxies (in separate terminal)
    bash ingestion/common/setup_local_proxy.sh

    # 2. Run this script
    uv run python ingestion/tenants/dev/a7753ab8-12e3-44f0-9ae6-9e85637b890e/test/_sample.py
"""

import json
import os
from pathlib import Path

from common.gcs import download_files
from common.gemini import analyze_images_with_structured_output
from common.isp import create_isp_client_from_env
from common.msqp import create_msqp_client_from_env
from common.utils import get_ingestion_root, get_tenant_dir
from dotenv import load_dotenv
from loguru import logger


def main():
    """Execute sample Gemini analysis."""
    project_root = get_ingestion_root()
    load_dotenv(project_root / ".env")

    # Configuration
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    env = os.getenv("ENV")
    bucket_name = f"zoolake-{env}.appspot.com"

    logger.info("=" * 80)
    logger.info("Gemini Image Analysis Sample (without Langfuse)")
    logger.info("=" * 80)

    # Step 1: Query MSQP for drawing file paths
    logger.info("\n[Step 1] Querying MSQP for drawing file paths...")
    msqp_client = create_msqp_client_from_env()
    msqp_client.use(catalog="drawing", schema="msqp__drawing")

    df = msqp_client.query("SELECT drawing_id, file_path FROM drawing_png_image order by created_at limit 2")

    if df.empty:
        logger.warning("No drawing file paths found.")
        return

    logger.info(f"✓ Found {len(df)} file paths")

    # Store drawing_ids for later use
    drawing_ids = df["drawing_id"].tolist()

    # Step 2: Download images from GCS
    logger.info("\n[Step 2] Downloading images from GCS...")
    gcs_paths = df["file_path"].tolist()
    logger.info("File paths from MSQP:")
    for gcs_path in gcs_paths:
        logger.info(f"  - {gcs_path}")

    # Extract bucket name and blob path from gs:// URLs
    blob_paths = []
    for gcs_path in gcs_paths:
        # Remove gs:// prefix and extract bucket/blob
        path_without_prefix = gcs_path.replace("gs://", "")
        # Split by first / to get bucket and blob path
        parts = path_without_prefix.split("/", 1)
        if len(parts) == 2:
            blob_paths.append(parts[1])
        else:
            logger.warning(f"Invalid GCS path format: {gcs_path}")

    local_paths = [Path("data") / blob_path.split("/")[-1] for blob_path in blob_paths]

    logger.info(f"Bucket: {bucket_name}")
    logger.info("Download target:")
    for blob_path, local_path in zip(blob_paths, local_paths):
        logger.info(f"  {blob_path} -> {local_path}")

    success_count, total_count = download_files(
        bucket_name=bucket_name,
        blob_paths=blob_paths,
        local_paths=local_paths,
        max_workers=4,
    )
    logger.info(f"✓ Downloaded {success_count}/{total_count} files to data/")

    # Step 3: Analyze images with Gemini (direct usage)
    logger.info(f"\n[Step 3] Analyzing images with Gemini ({model_name})...")

    # Filter existing files
    existing_paths = [p for p in local_paths if p.exists()]

    if not existing_paths:
        logger.warning("No files to analyze")
        return

    # Load system instruction from prompt.txt
    tenant_dir = get_tenant_dir()
    prompt_file = tenant_dir / "test" / "prompt.txt"
    if not prompt_file.exists():
        logger.error(f"prompt.txt not found at {prompt_file}")
        logger.error("Please create prompt.txt in the test directory")
        return

    system_instruction = prompt_file.read_text(encoding="utf-8").strip()
    logger.info(f"✓ Loaded prompt from {prompt_file}")

    # Define response schema directly (no Langfuse)
    response_schema = {
        "type": "object",
        "properties": {
            "drawing_type": {
                "type": "string",
                "description": "図面の種類（例: 部品図、組立図、回路図など）",
            },
            "description": {
                "type": "string",
                "description": "図面の全体的な説明",
            },
            "technical_elements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "技術的な要素のリスト（部品名、寸法、材料など）",
            },
            "important_information": {
                "type": "array",
                "items": {"type": "string"},
                "description": "重要な情報や注意事項のリスト",
            },
            "observations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "その他気づいた点のリスト",
            },
        },
        "required": [
            "drawing_type",
            "description",
            "technical_elements",
            "important_information",
            "observations",
        ],
    }

    try:
        # Analyze all images together
        result = analyze_images_with_structured_output(
            image_paths=existing_paths,
            system_instruction=system_instruction,
            response_schema=response_schema,
            model_name=model_name,
        )

        # Log results
        logger.info("✓ Analysis completed successfully")
        logger.info("\n" + "=" * 80)
        logger.info("Analysis Result:")
        logger.info("=" * 80)
        logger.info(f"\n{json.dumps(result, indent=2, ensure_ascii=False)}\n")

        # Step 4: Index to ISP
        logger.info("\n[Step 4] Indexing to ISP...")
        isp_client = create_isp_client_from_env()
        # ISP requires format: {name}_{tenant_id}
        # Format: drbfm-assist-[index_name]_{tenant_id}
        tenant_id = os.getenv("TENANT_ID")
        index_name = f"drbfm-assist-sample_{tenant_id}"

        # Define index mappings for drawing analysis
        mappings = {
            "properties": {
                "drawing_id": {"type": "string", "matching": ["exact"]},
                "drawing_type": {"type": "string", "matching": ["exact", "japanese"]},
                "description": {"type": "string", "matching": ["japanese"]},
                "technical_elements": {"type": "string", "matching": ["japanese"]},
                "important_information": {"type": "string", "matching": ["japanese"]},
                "observations": {"type": "string", "matching": ["japanese"]},
                "file_path": {"type": "string", "matching": ["exact"]},
                "analyzed_at": {"type": "string", "matching": ["exact"]},
            }
        }

        # Try to create index, delete and recreate if it already exists
        logger.info(f"Creating index '{index_name}'...")
        try:
            isp_client.create_index(index_name, mappings)
            logger.info(f"✓ Index '{index_name}' created")
        except Exception as e:
            if "409" in str(e) or "already_exists" in str(e).lower():
                logger.info(f"Index '{index_name}' already exists. Deleting to recreate...")
                isp_client.delete_index(index_name)
                logger.info(f"✓ Index '{index_name}' deleted")
                isp_client.create_index(index_name, mappings)
                logger.info(f"✓ Index '{index_name}' recreated")
            else:
                raise

        # Index documents for each drawing_id
        from datetime import datetime

        analyzed_at = datetime.now().isoformat()

        # Create a document for each drawing_id with the same analysis result
        for i, (drawing_id, file_path) in enumerate(zip(drawing_ids, gcs_paths)):
            document = {
                "drawing_id": drawing_id,
                "drawing_type": result.get("drawing_type", ""),
                "description": result.get("description", ""),
                "technical_elements": "\n".join(result.get("technical_elements", [])),
                "important_information": "\n".join(result.get("important_information", [])),
                "observations": "\n".join(result.get("observations", [])),
                "file_path": file_path,
                "analyzed_at": analyzed_at,
            }

            # Use drawing_id as document ID
            isp_client.index_document(index_name, drawing_id, document)
            logger.info(f"✓ Document indexed: {drawing_id}")

        logger.info(f"✓ Indexed {len(drawing_ids)} documents to ISP")

    except Exception as e:
        logger.error(f"Failed to analyze images: {e}", exc_info=True)


if __name__ == "__main__":
    main()
