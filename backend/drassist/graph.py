from drassist.chains.drbfm_assist import DrbfmAssistWorkflow
from drassist.chains.drbfm_batch import DrbfmBatchWorkflow
from drassist.chains.drbfm_workflow import DrbfmWorkflow

# 既存: 複数変更点分解機能あり (LLMで変更点抽出)
graph = DrbfmAssistWorkflow("configs/8d8232f3.yaml", "gemini-2.5-pro").create_workflow()

# 荏原向け: 単一変更点直接処理 (app_ebara.py と同様)
graph_ebara = DrbfmWorkflow("configs/8d8232f3.yaml", "gemini-2.5-pro").create_workflow()

# バッチ処理: 変更点リストを直接受け取り、Send APIで並列処理
graph_batch = DrbfmBatchWorkflow("configs/8d8232f3.yaml", "gemini-2.5-pro").create_workflow()
