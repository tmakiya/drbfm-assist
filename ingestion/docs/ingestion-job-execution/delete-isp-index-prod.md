# Prod環境でISP Indexを削除する手順

prod環境の踏み台サーバ経由でISP（Interactive Search Platform）の特定のindexを削除する手順です。

## 前提条件

- shoinyo9でzoolake folderの`roles/org_iam_bastion_accessor`の権限を取得済み
- 削除対象のindex名を把握している

## 概要

この作業は以下の流れで実施します：

1. **準備**: 踏み台サーバ接続とport-forward設定
2. **確認**: 削除対象indexの存在とデータ確認
3. **削除**: Index削除と確認

---

## 1. 準備

踏み台サーバに接続し、ISP APIへのport-forwardをバックグラウンドで開始します。

### 踏み台サーバに接続

```bash
PROJECT_ID=zoolake-prod
BASTION_NAME=$(gcloud compute instances list --project ${PROJECT_ID} \
  --filter="name~'zoolake.*bastion-[0-9a-z]{4}$'" \
  --format="get(name)" | head -1)
gcloud compute ssh ${BASTION_NAME} --project ${PROJECT_ID} --tunnel-through-iap
```

### kubectl contextを確認（contextが出力されない場合は、prod-job-execution.md 参照）

```bash
kubectl config get-contexts
```

**出力例:**

```bash
CURRENT   NAME                                       CLUSTER                                    AUTHINFO                                        NAMESPACE
*         gke_zoolake-prod_asia-northeast1_zoolake   gke_zoolake-prod_asia-northeast1_zoolake   gke_zoolake-prod_asia-northeast1_zoolake
```

### ISP APIへのport-forwardをバックグラウンドで開始

```bash
kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000 > /dev/null 2>&1 &
```

### 削除対象のindex名を設定

```bash
INDEX_NAME="削除したいindex名"
TENANT_ID=$(echo ${INDEX_NAME} | sed 's/.*_//')
```

### 設定確認

```bash
echo "Index: ${INDEX_NAME}"
echo "Tenant_ID: ${TENANT_ID}"
```

---

## 2. 削除前確認

### 2-1. Indexの存在確認

```bash
curl -s "http://localhost:3000/aliases/${INDEX_NAME}" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" | jq .
```

**出力例:**

```json
[
  { "alias": "削除したいIndex名" }
]
```

空配列 `[]` が返った場合、indexは存在しません。

**このtenantの全indexを確認したい場合**

```bash
# tenant_idで終わる全index
curl -s "http://localhost:3000/aliases/*_${TENANT_ID}" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" | jq .

# プレフィックスで検索
curl -s "http://localhost:3000/aliases/drbfm-*" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" | jq .
```

### 2-2. ドキュメント数確認

```bash
curl -s -X POST "http://localhost:3000/${INDEX_NAME}/_search" \
  -H "Content-Type: application/json" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" \
  -d '{"query": {"match_all": {}}, "size": 0}' | jq '.hits.total'
```

**出力例:** `17`

### 2-3. サンプルドキュメント確認【推奨】

```bash
# 1件だけ確認したい場合
curl -s -X POST "http://localhost:3000/${INDEX_NAME}/_search" \
  -H "Content-Type: application/json" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" \
  -d '{"query": {"match_all": {}}, "size": 1}' | jq '.hits.hits[0]._source'

# 複数件確認したい場合（3件）
curl -s -X POST "http://localhost:3000/${INDEX_NAME}/_search" \
  -H "Content-Type: application/json" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" \
  -d '{"query": {"match_all": {}}, "size": 3}' | jq '.hits.hits[]._source'
```

---

## 3. Index削除

### 3-1. Index削除実行

⚠️ **警告: この操作は取り消せません。手順2で確認した内容が正しいことを確認してから実行してください。**

```bash
curl -s -X DELETE "http://localhost:3000/${INDEX_NAME}" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" | jq .
```

**出力例（成功時）:**

```json
{
  "alias": "削除したいindex名"
}
```

---

### 3-2. 削除確認

```bash
curl -s "http://localhost:3000/aliases/${INDEX_NAME}" \
  -H "x-caddi-tenant-id: ${TENANT_ID}" | jq .
```

**出力例:** `[]`

空配列が返れば削除成功です。



---

## トラブルシューティング

### エラー: "missing_tenant_id"

```json
{ "statusCode": 403, "error": { "type": "missing_tenant_id" } }
```

**原因**: `x-caddi-tenant-id` ヘッダーが欠落

**対処**: 全curlコマンドに `-H "x-caddi-tenant-id: ${TENANT_ID}"` を追加。TENANT_IDが正しく設定されているか確認。

---

### エラー: "not_found"

```json
{ "statusCode": 404, "error": { "type": "not_found" } }
```

**原因**: Indexが存在しないか、index名が間違っている

**対処**: INDEX_NAMEが正しいか確認

---

### エラー: "Connection refused"

```
curl: (7) Failed to connect to localhost port 3000
```

**原因**: port-forwardが動作していない

**対処**:

```bash
# port-forwardプロセスが実行中か確認
ps -p ${PORT_FORWARD_PID} > /dev/null && echo "Running" || echo "Not running"

# port 3000が使用されているか確認
lsof -i :3000 || ss -tlnp | grep 3000

# サービス名を確認
kubectl get svc -n isp-agent-platform

# port-forwardを再起動
kill ${PORT_FORWARD_PID} 2>/dev/null
kubectl port-forward -n isp-agent-platform svc/isp-api 3000:3000 > /dev/null 2>&1 &
PORT_FORWARD_PID=$!
sleep 2
```

---

## 関連ドキュメント

- [prod-job-execution.md](./prod-job-execution.md) - Prod環境での基本的なkubectl操作
- [kubectl_commands.md](./kubectl_commands.md) - kubectl基本コマンド
