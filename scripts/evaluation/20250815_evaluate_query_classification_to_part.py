import click
import pandas as pd
from dotenv import load_dotenv
from langfuse import get_client
from loguru import logger
from tqdm import tqdm

from drassist.llm import GeminiClient

load_dotenv()

UNIT_LIST = [
    "ブーム装置",
    "ジブ伸縮機構（テレスコープ）",
    "ジブ取付・格納機構",
    "ジブ角度・チルト機構",
    "ラフィングジブ",
    "シングルトップジブ",
    "ブーム起伏装置",
    "折曲装置",
    "旋回装置",
    "ウインチ装置",
    "フック装置",
    "アウトリガ装置",
    "カウンタウエイト装置",
    "キャブ装置",
    "コックピット制御システム",
    "外装装置",
    "昇降経路",
    "フレーム",
    "走行装置",
    "ドライブトレイン",
    "舵取装置",
    "制動装置",
    "緩衝装置",
    "エンジン系",
    "上部パワートレーン（ePTO）",
    "油圧装置",
    "空圧装置",
    "電装／電送装置",
    "充電装置",
    "照明装置",
    "空調装置",
    "過負荷防止装置（AML）",
    "動作規制装置（AMC）",
    "範囲規制装置（AWL）",
    "巻過防止・インタロック類",
    "アタッチメント装置",
    "バケット装置",
    "レベリング装置",
    "リフト装置",
    "ラジコン・リモコン装置",
    "コンクリート圧送装置",
    "塗装全般",
    "銘板装置",
    "低騒音装置",
    "牽引装置",
    "アシストカー",
    "パッケージ装置",
    "その他オプション",
]


@click.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--prompt-version", type=int, default=2, help="Langfuse prompt version to use")
def main(csv_path, prompt_version):
    category_list = UNIT_LIST

    langfuse_client = get_client()

    langfuse_prompt = langfuse_client.get_prompt("Categorize query by part", version=prompt_version)
    response_schema = langfuse_prompt.config["response_schema"]
    system_instruction = langfuse_prompt.compile(category_list=category_list)

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

    logger.info(df["categories"].to_string(index=False))
    evaluation_result = df.apply(lambda x: x["原因_ユニット"] in x["categories"], axis=1)
    logger.info(evaluation_result.to_string(index=False))


if __name__ == "__main__":
    main()
