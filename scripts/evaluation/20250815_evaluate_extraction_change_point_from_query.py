import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import get_client
from loguru import logger
from tqdm import tqdm

from drassist.llm import GeminiClient

load_dotenv()


@click.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--prompt-version", type=int, default=1, help="Langfuse prompt version to use")
def main(csv_path, prompt_version):
    langfuse_client = get_client()

    langfuse_prompt = langfuse_client.get_prompt("Extract change point from query", version=prompt_version)
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile()

    gemini_client = GeminiClient(
        model_name="gemini-2.5-flash",
        location="us-central1",
        temperature=0,
        seed=42,
    )

    df = pd.read_csv(csv_path)

    results = []
    for _, row in tqdm(df.iterrows()):
        change_point = row["変更点"]
        prompt_text = f"Query: {change_point}"

        # Generate structured content using Gemini client
        result = gemini_client.generate_structured_content(
            prompt=prompt_text,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )
        results.append(result)

    results = pd.DataFrame(results)
    df = pd.concat([df, results], axis=1)

    logger.info(df["change_target"].to_string(index=False))
    logger.info(df["change_point"].to_string(index=False))


if __name__ == "__main__":
    main()
