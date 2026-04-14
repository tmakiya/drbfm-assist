# 新規テナント追加手順

このドキュメントでは、新規テナントを追加する手順を説明します。


## 手順1. Client 申請

### 1.1 MSQP への申請

**Why**: GKE job が MSQP 経由でデータをクエリするために必要です。

**What**: MSQP にアクセスするための client_id と client_secret の発行を依頼します。

1. 新規追加するテナントの client_id を決定する（任意ですが、`agent-ingest-{tenant_id の前半}` の形式を推奨）
2. Slack の #tech-grp-infrastructure チャンネルで発行を依頼する

（例: https://caddijp.slack.com/archives/C094LBZM7CJ/p1765513680360569）


### 1.2 M2M token issuer への申請

**Why**: GKE job が ISP（interactive-search-platform）にデータを投入するために必要です。

**What**: M2M token issuer からトークンを取得するための client_id と client_secret の発行を依頼します。

1. 新規追加するテナントの client_id を決定する（任意ですが、`agent-ingest-{tenant_id の前半}` の形式を推奨）
2. [Internal Token 用のクライアント発行リクエスト](https://backstage.caddi.io/catalog/default/component/m2m-token-issuer/docs/ja/internal_token/request/) に従い発行を依頼する

（例: https://caddijp.slack.com/archives/C08P6NE912A/p1766042767512329 ※ このslack依頼は、client_id の命名規則が推奨と違うので注意してください）



## 手順2. zoolake-infra と zoolake-cluster-config への PR 作成
※ 便宜上、手順1 と 手順2 を分けていますが、同時に行って問題ありません。

### 2.1 zoolake-infra への PR 作成

**Why**: GKE job が使用するサービスアカウントやシークレットを作成するために必要です。

**What**: zoolake-infra リポジトリに PR を作成します。

※ production 環境への反映は製品のリリースサイクルに依存します。余裕をもって作業してください。

1. [terraform/environments/prod/data-plane/infra/agent-ingestion-infra.tf](https://github.com/caddijp/zoolake-infra/blob/develop/terraform/environments/prod/data-plane/infra/agent-ingestion-infra.tf) に tenant_id を追加する

（例: https://github.com/caddijp/zoolake-infra/pull/5052）


### 2.2 zoolake-cluster-config への PR 作成

**Why**: GKE job を作成するために必要です。

**What**: zoolake-cluster-config リポジトリに PR を作成します。

※ production 環境への反映は製品のリリースサイクルに依存します。余裕をもって作業してください。

1. [applications/agent-ingestion-infra/overlays/prod/drbfm-{short_tenant_id}.yml](https://github.com/caddijp/zoolake-cluster-config/tree/feature/refactor-argocd-directory/applications/agent-ingestion-infra/overlays/prod) に設定ファイルを追加する
2. 以下の項目が正しく設定されていることを確認する：
    - `short_tenant_id` は `tenant_id` の前半部分を使用する（例: tenant_id が `a7753ab8-1234-5678-90ab-cdef12345678` の場合、`short_tenant_id` は `a7753ab8`）
    - `tenant_id`、`ENV`、サービスアカウント名が意図した値になっていることを確認する
    - サービスアカウント名は zoolake-infra で作成したものを指定する（デフォルト: `sa-agent-ingest-{SHORT_TENANT_ID}@{PROJECT_ID}.iam.gserviceaccount.com`）
3. [applications/agent-ingestion-infra/overlays/prod/kustomization.yaml](https://github.com/caddijp/zoolake-cluster-config/blob/main/applications/agent-ingestion-infra/overlays/prod/kustomization.yaml) に作成したファイルを追加する

（例: https://github.com/caddijp/zoolake-cluster-config/pull/4641/commits/22af98d32f0b8d0d414b08b756996fb680ec9514）



## 手順3. Google Cloud の Secret Manager へのシークレット追加
※ zoolake-infra が prod へリリースされた後に行ってください。

**Why**: GKE job が使用するシークレットを Secret Manager に追加するために必要です。

**What**: Google Cloud の Secret Manager に手順1 で発行してもらった、MSQP と M2M token issuer のシークレットを追加します。

1. [shoninyo9](https://caddijp.atlassian.net/wiki/spaces/TECH/pages/1125293838/Just-In-Time+Access+System)から、zoolake folder の roles/secretmanager.secretVersionAdder の権限を依頼する
2. 上記の依頼が承認されたら、zoolake-prod の Google Cloud Console にアクセスし、Secret Manager を開く
3. 手順2 で作成された シークレットを探す。デフォルトなら以下の名前で作成されています：
    - MSQP: `agent-ingest-msqp-client-secret-{SHORT_TENANT_ID}`
    - M2M token issuer: `agent-ingest-m2m-internal-token-client-secret-{SHORT_TENANT_ID}`
4. それぞれのシークレットに対して、手順1 で発行してもらった client_secret を登録する



## 手順4. 確認

以下の URL から ArgoCD の状態を確認し、同期が成功していることを確認します。
※ シークレットの反映やらでしばらく時間がかかる場合があります。

https://prod-argocd.zoolake.jp/applications/agent-ingestion-infra?orphaned=false&resource=
