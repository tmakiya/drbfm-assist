# ===========================
# Stage 1: 依存関係のインストール
# ===========================
FROM node:24-bookworm AS deps
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# ===========================
# Stage 2: ビルド
# ===========================
FROM node:24-bookworm AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next.jsのビルド（standalone出力を生成）
# NEXT_PUBLIC_* 環境変数はビルド時に必要
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

ARG NEXT_PUBLIC_BASE_PATH
ENV NEXT_PUBLIC_BASE_PATH=${NEXT_PUBLIC_BASE_PATH:-""}

RUN npm run build

# ===========================
# Stage 3: 本番環境実行
# ===========================
FROM node:24-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production

# セキュリティのため非rootユーザーを作成
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 必要なファイルのみをコピー
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 本番サーバー起動
CMD ["node", "server.js"]
