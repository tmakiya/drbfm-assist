# データ取り込みジョブの手動実行手順

このドキュメントでは、STG のDRBFM データ取り込みジョブ（CronJob）を手動で実行する方法を説明します。
※ dev と異なり、stg では踏み台サーバ経由で kubectl を実行する必要があります。


## 前提条件
- zoolake-stg-e3979 の踏み台サーバにSSH接続できること

## 踏み台サーバに SSH接続

```bash
PROJECT_ID=zoolake-stg-e3979
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
gcloud container clusters get-credentials zoolake --region asia-northeast1 --project zoolake-stg-e3979 --internal-ip
```

```bash
kubectl config get-contexts
```

**出力例:**
```
CURRENT   NAME                                            CLUSTER                                         AUTHINFO                                        NAMESPACE
*         gke_zoolake-stg-e3979_asia-northeast1_zoolake   gke_zoolake-stg-e3979_asia-northeast1_zoolake   gke_zoolake-stg-e3979_asia-northeast1_zoolake
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


##  基本的な kubectl の操作

以降は、[kubectl_commands.md](./kubectl_commands.md) を参照してください。
