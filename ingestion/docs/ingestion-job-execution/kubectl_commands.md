#  基本的な kubectl の操作


## Job を実行

以下のコマンドを実行するだけです（`a7753ab8` を対象のテナントIDに置き換えてください）：

```bash
TENANT_ID=a7753ab8
```

```bash
kubectl create job -n agent-ingestion-infra --from=cronjob/drbfm-ingestion-${TENANT_ID} drbfm-ingestion-${TENANT_ID}-$(date +%Y%m%d-%H%M%S)
```

実行すると以下のように表示されます：

```
job.batch/drbfm-ingestion-manual-20251216-143000 created
```

## 実行状況の確認

### Job の一覧を確認

```bash
kubectl get jobs -n agent-ingestion-infra
```

**出力例:**
```
NAME                                              STATUS     COMPLETIONS   DURATION   AGE
drbfm-ingestion-manual-20251216-143000           Complete   1/1           25s        2m
```

- `STATUS: Complete` → 成功
- `STATUS: Failed` → 失敗
- `COMPLETIONS: 0/1` → 実行中

### ログを確認

```bash
# 最新のログをリアルタイムで表示（Job名は上記で確認したものを使用）
kubectl logs -n agent-ingestion-infra -l drbfm-ingestion-a7753ab8-20251224-122451 -f
```

`-f` オプションを外すと、これまでのログのみ表示されます。

### 詳細情報を確認（エラー時）

```bash
kubectl describe job -n agent-ingestion-infra drbfm-ingestion-a7753ab8-20251224-122451
```

## 環境変数を変更して実行

環境変数を追加・変更してjobを実行したい場合（例: ログレベルをDEBUG、クエリ数を2に制限）：
※ cronjob への影響はありません。

```bash
kubectl create job drbfm-ingestion-${TENANT_ID}-manual-debug-$(date +%Y%m%d-%H%M%S) \
  --from=cronjob/drbfm-ingestion-${TENANT_ID} \
  -n agent-ingestion-infra \
  --dry-run=client -o json \
| jq '
  .spec.template.spec.containers[0].env |=
  map(select(.name != "LOGURU_LEVEL" and .name != "QUERY_FILE_LIMIT"))
  + [
    {"name":"LOGURU_LEVEL","value":"DEBUG"},
    {"name":"QUERY_FILE_LIMIT","value":"2"}
  ]
' \
| kubectl apply -f -
```

**環境変数を変更するには:**
- `map(select(...))` の部分に変更したい変数名を追加（既存値を削除）
- 配列に新しい環境変数を追加: `{"name":"変数名","value":"値"}`
- 複数の環境変数はカンマで区切る


## Job を削除

```bash
# 特定の Job を削除
kubectl delete job -n agent-ingestion-infra drbfm-ingestion-a7753ab8-20251224-122451

# 失敗した Job をまとめて削除
kubectl delete job -n agent-ingestion-infra --field-selector status.successful=0
```


## トラブルシューティング

### Job が失敗する場合

1. ログを確認:
```bash
kubectl logs -n agent-ingestion-infra -l job-name=<job-name>
```

2. Pod の状態を確認:
```bash
kubectl get pods -n agent-ingestion-infra -l job-name=<job-name>
```

3. Pod の詳細を確認:
```bash
kubectl describe pod -n agent-ingestion-infra -l job-name=<job-name>
```

### Pod に入ってデバッグ

実行中の Pod の中に入って調査したい場合（完了した Pod には入れません）:


**1. Pod一覧を確認**

```bash
kubectl get pods -n agent-ingestion-infra
```

**2. Pod名を指定して入る**

```bash
kubectl exec -it -n agent-ingestion-infra <pod-name> -- /bin/bash
```

**3. Job名から直接入る（便利）**

```bash
kubectl exec -it -n agent-ingestion-infra \
  $(kubectl get pod -n agent-ingestion-infra -l job-name=<job-name> -o jsonpath='{.items[0].metadata.name}') \
  -- /bin/bash
```

**例:**
```bash
kubectl exec -it -n agent-ingestion-infra \
  $(kubectl get pod -n agent-ingestion-infra -l job-name=drbfm-ingestion-a7753ab8-manual-20251216-143000 -o jsonpath='{.items[0].metadata.name}') \
  -- /bin/bash
```

Pod から出るには `exit` または `Ctrl+D` を押します。


## よくある質問

**Q: CronJob が自動実行されないのはなぜ？**

A: `suspend: true` に設定されているため、手動実行専用となっています。

**Q: Job の実行履歴はどこで確認できる？**

A: web UI からみるか、`kubectl get jobs -n agent-ingestion-infra` で過去の Job が表示されます。履歴は成功した Job が3件、失敗した Job が3件まで保存されます。
