# データ取り込みジョブの手動実行手順

Ingestion Job を実行するには、ArgoCD の Web UI または kubectl コマンドの 2つの方法があります。

基本的には、ArgoCD の Web UI からの実行を推奨しますが、debug の際に環境変数や引数を変えて実行したいときは、kubectl コマンドでの実行を行ってください。

# ArgoCD の Web UI からの手動実行

## 前提

- github の [agent-ingestion-editor](https://github.com/orgs/caddijp/teams/agent-ingestion-editor) チームのメンバーであること
- ArgoCD の Web UI にアクセスできること（[https://prod-argocd.zoolake.jp/](https://prod-argocd.zoolake.jp/applications/agent-ingestion-infra?orphaned=false&resource=)）


1. ArgoCD の Web UI にアクセスし、実行したい CronJob  を探す。通常は、drbfm-ingestion-{TENANT_ID} という名前になっています。
2. 三点リーダ ⇒ Create Job をクリック

以上です。


# kubectl からの手動実行手順

このドキュメントでは、 のDRBFM データ取り込みジョブ（CronJob）を手動で実行する方法を説明します。
※ dev と異なり、prod では踏み台サーバ経由で kubectl を実行する必要があります。

## shoinyo9 で、prod の踏み台サーバにアクセスする一時的な権限を申請/取得する

[shoninyo9](https://caddijp.atlassian.net/wiki/spaces/TECH/pages/1125293838/Just-In-Time+Access+System)から、zoolake folder の roles/org_iam_bastion_accessor の権限を依頼する

※ 以降の手順を実行するには、この権限が必要です。

## 踏み台サーバに SSH接続

```bash
PROJECT_ID=zoolake-prod
```

```bash
BASTION_NAME=$(gcloud compute instances list --project ${PROJECT_ID} \
  --filter="name~'zoolake.*bastion-[0-9a-z]{4}$'" \
  --format="get(name)" | head -1)
```

```bash
gcloud compute ssh ${BASTION_NAME} --project ${PROJECT_ID} --tunnel-through-iap
```


## 踏み台サーバ上で、kubectl context の設定（初回のみ）

踏み台サーバ上で、対象のクラスタに接続するために kubectl context を設定します。

### 必要な認証や設定のインストール

指示に従って 認証をする

```bash
gcloud auth login
```

stg 環境の context を取得

```bash
gcloud container clusters get-credentials zoolake --region asia-northeast1 --project zoolake-prod --internal-ip
```

```bash
kubectl config get-contexts
```

**出力例:**
```
CURRENT   NAME                                       CLUSTER                                    AUTHINFO                                        NAMESPACE
*         gke_zoolake-prod_asia-northeast1_zoolake   gke_zoolake-prod_asia-northeast1_zoolake   gke_zoolake-prod_asia-northeast1_zoolake
```

クラスターに接続できたか確認

```bash
kubectl get ns
```

**出力例:**
```
NAME                        STATUS   AGE
anchor                      Active   188d
argo-rollouts               Active   231d
argocd                      Active   231d
auth                        Active   231d
cert-manager                Active   59d
```


## 基本的な kubectl の操作

以降は、[kubectl_commands.md](./kubectl_commands.md) を参照してください。
