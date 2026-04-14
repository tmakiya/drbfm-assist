#!/bin/bash
# 仮想環境セットアップスクリプト

echo "🚀 仮想環境をセットアップします..."

# 仮想環境の名前
VENV_NAME="venv"

# 仮想環境が既に存在する場合は削除
if [ -d "$VENV_NAME" ]; then
    echo "⚠️  既存の仮想環境を削除します..."
    rm -rf "$VENV_NAME"
fi

# Python 3.8以上がインストールされているか確認
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3がインストールされていません。"
    exit 1
fi

# Pythonバージョンを確認
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "📌 Python バージョン: $(python3 --version)"

# 仮想環境を作成
echo "📦 仮想環境を作成中..."
python3 -m venv "$VENV_NAME"

# 仮想環境をアクティベート
echo "🔌 仮想環境をアクティベート中..."
source "$VENV_NAME/bin/activate"

# pipをアップグレード
echo "⬆️  pipをアップグレード中..."
pip install --upgrade pip

# requirements.txtからパッケージをインストール
if [ -f "requirements.txt" ]; then
    echo "📥 依存パッケージをインストール中..."
    pip install -r requirements.txt
    echo "✅ パッケージのインストールが完了しました！"
else
    echo "⚠️  requirements.txtが見つかりません。"
fi

echo ""
echo "✅ 仮想環境のセットアップが完了しました！"
echo ""
echo "📝 使用方法:"
echo "   source $VENV_NAME/bin/activate  # 仮想環境をアクティベート"
echo "   streamlit run app_suzuki_agents_v1.py  # アプリを実行"
echo "   deactivate  # 仮想環境を無効化"
echo ""

