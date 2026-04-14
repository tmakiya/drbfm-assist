# データ取り込みジョブの手動実行手順

このドキュメントでは、DEV のDRBFM データ取り込みジョブ（CronJob）を手動で実行する方法を説明します。


## 前提条件
- `kubectl` コマンドラインツールがインストールされていること
- zoolake-dev プロジェクトに対する権限があり、gcloud auth login が完了していること


## kubectl context の設定

まず、対象のクラスタに接続するために kubectl context を設定します。

### 利用可能な context を確認

```bash
kubectl config get-contexts
```

**出力例:**
```
CURRENT   NAME                                            CLUSTER                                         AUTHINFO                                        NAMESPACE
*         gke_zoolake-dev_asia-northeast1_zoolake         gke_zoolake-dev_asia-northeast1_zoolake         gke_zoolake-dev_asia-northeast1_zoolake
```

`*` マークが現在選択されている context です。

### context を切り替え

```bash
# dev環境に切り替え
kubectl config use-context gke_zoolake-dev_asia-northeast1_zoolake

```

### GKE から認証情報を再取得（必要な場合）

context が存在しない場合や認証情報が古い場合は、GKE から再取得します：

```bash
# dev環境
gcloud container clusters get-credentials zoolake --region=asia-northeast1 --project=zoolake-dev
```

##  基本的な kubectl の操作

以降は、[kubectl_commands.md](./kubectl_commands.md) を参照してください。
