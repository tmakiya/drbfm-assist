#!/bin/bash

# DRBFM Assist Development Helper Script
# GitHub 連携と開発ワークフローを簡素化

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${GREEN}=== $1 ===${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Main menu
show_menu() {
    echo ""
    print_header "DRBFM Assist Development Menu"
    echo "1. Setup - 初期セットアップ（依存関係のインストール）"
    echo "2. Quality Check - コード品質チェック"
    echo "3. Test - テスト実行"
    echo "4. New Feature - 新機能ブランチを作成"
    echo "5. Push Changes - 変更をプッシュ"
    echo "6. Create PR - プルリクエストを作成"
    echo "7. Update Branch - リモート更新を取得"
    echo "8. Git Status - Git ステータス確認"
    echo "9. Help - コマンドのヘルプを表示"
    echo "0. Exit - 終了"
    echo ""
}

# Setup environment
setup() {
    print_header "Initializing Environment"
    
    if [ ! -f .env ]; then
        if [ -f .env.sample ]; then
            print_info "Creating .env from .env.sample"
            cp .env.sample .env
            print_success ".env created"
            print_info "Please edit .env with your credentials"
        else
            print_error ".env.sample not found"
        fi
    fi
    
    print_info "Installing dependencies with uv..."
    if [ -d backend ]; then
        cd backend
        uv sync
        cd ..
        print_success "Backend dependencies installed"
    fi
    
    print_info "Installing additional tools..."
    uv run pre-commit install 2>/dev/null || true
    
    print_success "Setup complete!"
}

# Run quality checks
quality_check() {
    print_header "Running Code Quality Checks"
    
    if [ ! -d backend ]; then
        print_error "backend directory not found"
        return 1
    fi
    
    cd backend
    
    # Ruff check
    print_info "Running ruff check..."
    uv run ruff check . || {
        print_error "Ruff check failed"
        cd ..
        return 1
    }
    print_success "Ruff check passed"
    
    # Ruff format check
    print_info "Running ruff format check..."
    uv run ruff format --check . || {
        print_info "Auto-formatting code..."
        uv run ruff format .
        print_success "Code formatted"
    }
    
    # Pre-commit
    print_info "Running pre-commit hooks..."
    pre-commit run --all-files || print_info "Some pre-commit checks may have warnings (review manually)"
    
    cd ..
    print_success "Quality checks complete!"
}

# Run tests
run_tests() {
    print_header "Running Tests"
    
    if [ ! -d backend ]; then
        print_error "backend directory not found"
        return 1
    fi
    
    cd backend
    
    if [ -d tests ]; then
        print_info "Running pytest..."
        uv run pytest tests/ -v
        print_success "Tests completed"
    else
        print_info "No tests directory found"
    fi
    
    cd ..
}

# Create new feature branch
create_feature_branch() {
    print_header "Create New Feature Branch"
    
    read -p "Enter feature name (e.g., add-fuzzy-search): " feature_name
    
    if [ -z "$feature_name" ]; then
        print_error "Feature name cannot be empty"
        return 1
    fi
    
    branch_name="feature/${feature_name}"
    
    print_info "Creating branch: $branch_name"
    git checkout -b "$branch_name"
    print_success "Branch created: $branch_name"
    
    echo ""
    print_info "Next steps:"
    echo "1. Make your changes"
    echo "2. Run: ./dev-script.sh (choice 2 or 3 for quality checks)"
    echo "3. Commit: git add . && git commit -m 'feat: your message'"
    echo "4. Push: ./dev-script.sh (choice 5)"
    echo "5. Create PR: ./dev-script.sh (choice 6)"
}

# Push changes
push_changes() {
    print_header "Push Changes to GitHub"
    
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    if [ "$current_branch" = "main" ]; then
        print_error "Cannot push directly to main branch!"
        return 1
    fi
    
    print_info "Current branch: $current_branch"
    
    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        read -p "You have uncommitted changes. Commit them first? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -p "Enter commit message: " commit_msg
            git add .
            git commit -m "$commit_msg"
        else
            print_error "Please commit your changes first"
            return 1
        fi
    fi
    
    print_info "Pushing to origin/$current_branch..."
    git push -u origin "$current_branch"
    print_success "Pushed successfully!"
}

# Create PR
create_pr() {
    print_header "Create Pull Request"
    
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    if [ "$current_branch" = "main" ]; then
        print_error "Cannot create PR from main branch"
        return 1
    fi
    
    # Check if GitHub CLI is available
    if ! command -v gh &> /dev/null; then
        print_error "GitHub CLI (gh) is not installed"
        echo "Install it from: https://cli.github.com"
        return 1
    fi
    
    print_info "Creating PR for branch: $current_branch"
    
    read -p "Enter PR title: " pr_title
    read -p "Enter PR description (optional): " pr_description
    
    if [ -z "$pr_title" ]; then
        print_error "PR title cannot be empty"
        return 1
    fi
    
    gh pr create --title "$pr_title" --body "$pr_description" --base main
    print_success "PR created!"
}

# Update branch
update_branch() {
    print_header "Update Branch from Remote"
    
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    
    print_info "Fetching from remote..."
    git fetch origin
    
    print_info "Updating $current_branch..."
    git pull origin "$current_branch"
    
    print_success "Branch updated!"
}

# Git status
git_status() {
    print_header "Git Status"
    git status
    echo ""
    print_header "Recent Commits"
    git log --oneline -10
}

# Show help
show_help() {
    cat << EOF
${GREEN}DRBFM Assist Development Helper${NC}

${YELLOW}Available Commands:${NC}

Setup & Quality:
  ./dev-script.sh setup       - 初期セットアップ
  ./dev-script.sh quality     - コード品質チェック
  ./dev-script.sh test        - テスト実行

Development:
  ./dev-script.sh feature     - 新機能ブランチを作成
  ./dev-script.sh push        - 変更をプッシュ
  ./dev-script.sh pr          - プルリクエストを作成

Git:
  ./dev-script.sh update      - リモート更新を取得
  ./dev-script.sh status      - Git ステータス確認
  ./dev-script.sh help        - このヘルプを表示

${YELLOW}Example Workflow:${NC}

  1. ./dev-script.sh setup
  2. ./dev-script.sh feature
  3. (Make your changes)
  4. ./dev-script.sh quality
  5. git add . && git commit -m "feat: your message"
  6. ./dev-script.sh push
  7. ./dev-script.sh pr

EOF
}

# Main script logic
if [ $# -eq 0 ]; then
    # Interactive mode
    while true; do
        show_menu
        read -p "Enter your choice [0-9]: " choice
        
        case $choice in
            1) setup ;;
            2) quality_check ;;
            3) run_tests ;;
            4) create_feature_branch ;;
            5) push_changes ;;
            6) create_pr ;;
            7) update_branch ;;
            8) git_status ;;
            9) show_help ;;
            0) print_success "Goodbye!"; exit 0 ;;
            *) print_error "Invalid choice. Please try again." ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
else
    # Command mode
    case "$1" in
        setup) setup ;;
        quality|check) quality_check ;;
        test) run_tests ;;
        feature) create_feature_branch ;;
        push) push_changes ;;
        pr) create_pr ;;
        update) update_branch ;;
        status) git_status ;;
        help) show_help ;;
        *) show_help ;;
    esac
fi
