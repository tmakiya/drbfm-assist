# Defects Pipeline

故障ドキュメント画像を解析し、構造化データとしてISP（Interactive Search Platform）にインデックスするパイプライン。

## 処理フロー

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DefectsPipeline.run()                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Fetching (fetching.py)                                                   │
│    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐       │
│    │  MSQP クエリ    │ -> │  図面データ取得  │ -> │  GCS から画像   │       │
│    │  (query.sql)    │    │                 │    │  ダウンロード   │       │
│    └─────────────────┘    └─────────────────┘    └─────────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ DataFrame (drawing_id, original_id, local_path, ...)
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Grouping (processing.py)                                                 │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │  original_id でグループ化（複数ページの図面を1つにまとめる）    │     │
│    └─────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ List[{original_id, image_paths, drawing_ids}]
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Image Analysis (processing.py)                                           │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │  Gemini API で画像解析（並列処理）                              │     │
│    │  - 原因ユニット/部品の抽出                                      │     │
│    │  - 故障モード/影響の抽出                                        │     │
│    │  - 対策方法の抽出                                               │     │
│    └─────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ List[{original_id, cause_unit, cause_part, ...}]
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Embedding Generation (processing.py)                                     │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │  unit_part_change テキストからベクトル埋め込みを生成            │     │
│    │  (gemini-embedding-001, 3072次元)                               │     │
│    └─────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ DataFrame with embedding column
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. ISP Ingestion (ingest.py)                                                │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │  ISP にドキュメントをインデックス                               │     │
│    │  - インデックス作成/更新                                        │     │
│    │  - ドキュメントのバルクインデックス                             │     │
│    └─────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## コンポーネント

### pipeline.py - DefectsPipeline

パイプライン全体を統括するメインクラス。

- `BasePipeline` を継承
- 各コンポーネントを順番に呼び出し
- エラー集計とCSV出力
- `PipelineResult` を返却

### config.py - PipelineConfig

パイプラインの設定を管理。

| 設定項目 | 説明 |
|---------|------|
| `pipeline_dir` | テナント固有の設定ディレクトリ |
| `system_instruction` | Gemini用プロンプト（unit_list置換済み） |
| `response_schema` | Gemini構造化出力のスキーマ |
| `bucket_name` | GCSバケット名 |
| `model_name` | Geminiモデル名（環境変数で指定可） |
| `limit` | クエリ結果の上限数 |
| `max_workers` | 並列処理のワーカー数 |

### fetching.py - fetch_drawings

MSQPから図面データを取得し、GCSから画像をダウンロード。

```python
def fetch_drawings(config: PipelineConfig) -> pd.DataFrame
```

- MSQPクエリ実行（`query.sql`使用）
- GCSから画像ファイルをローカルにダウンロード
- `local_path` カラムを追加したDataFrameを返却

### processing.py - 画像解析・埋め込み生成

#### group_drawings_by_original_id

```python
def group_drawings_by_original_id(drawing_df: pd.DataFrame) -> List[Dict]
```

複数ページの図面を `original_id` でグループ化。

#### analyze_groups_parallel

```python
def analyze_groups_parallel(
    groups: List[Dict],
    image_analysis_config: ImageAnalysisConfig,
) -> tuple[pl.DataFrame, Dict[str, int]]
```

Gemini APIで画像を並列解析。50MB制限チェック付き。
成功分のDataFrameと、件数サマリを返却。

#### build_dataframe_with_embeddings

```python
def build_dataframe_with_embeddings(
    df: pl.DataFrame,
    embedding_config: EmbeddingConfig,
) -> tuple[pl.DataFrame, Dict[str, int]]
```

解析結果からDataFrameを作成し、埋め込みベクトルを生成。

### ingest.py - ISPインデックス

#### ingest_dataframe_to_isp

```python
def ingest_dataframe_to_isp(
    df: pd.DataFrame,
    isp_config: IspConfig,
    pipeline_dir: Path,
    truncate: bool = False,
    dry_run: bool = False,
) -> dict
```

DataFrameをISPにインデックス。

- `truncate=True`: インデックスを削除して再作成
- `dry_run=True`: 実際のインデックスは行わずJSONに出力

## テナント設定ファイル

各テナントディレクトリに以下のファイルが必要:

```
tenants/{env}/{tenant_id}/defects/
├── config.yml     # パイプライン設定
├── query.sql      # MSQP クエリ
└── main.py        # エントリポイント
```

### config.yml の構成

```yaml
# Gemini プロンプトに挿入するユニットリスト
unit_list:
  - ユニット1
  - ユニット2

# Gemini 構造化出力スキーマ
gemini:
  response_schema:
    type: object
    properties:
      cause_unit:
        type: string
      # ...

# ISP インデックス設定
isp:
  index_name: defects
  fields:
    # フィールドマッピング
  settings:
    # Elasticsearch設定
  mappings:
    # インデックスマッピング
```

## 使用方法

```bash
# 通常実行
cd ingestion
uv run python tenants/dev/{tenant_id}/defects/main.py

# ドライラン（ISP操作をスキップ）
uv run python tenants/dev/{tenant_id}/defects/main.py --dry-run

# インデックス再作成
uv run python tenants/dev/{tenant_id}/defects/main.py --truncate
```

## エラーハンドリング

エラーは3種類に分類され、CSVファイルに出力:

| ステータス | 説明 |
|-----------|------|
| `skipped_large_file` | 50MB制限超過でスキップ |
| `image_analysis_error` | Gemini API エラー |
| `embedding_error` | 埋め込み生成エラー |

出力先: `{pipeline_dir}/error/error_{timestamp}.csv`
