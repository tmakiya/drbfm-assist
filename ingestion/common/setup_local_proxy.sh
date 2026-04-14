#!/bin/bash
# Setup SOCKS5 proxy and kubectl port-forward for local development
#
# This script sets up:
# 1. SOCKS5 proxy via bastion for MSQP access (localhost:1080)
# 2. kubectl port-forward for ISP API access (localhost:3000)
#
# Usage:
#   bash setup_local_proxy.sh
#
# To stop:
#   Press Ctrl+C (kills both processes)

set -e
PROJECT_ID="zoolake-dev"

ISP_NAMESPACE=${ISP_NAMESPACE:-isp-agent-platform}
ISP_SERVICE=${ISP_SERVICE:-isp-api}
ISP_PORT=${ISP_PORT:-3000}

# Cleanup function to kill background processes
cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ ! -z "$PROXY_PID" ] && kill -0 $PROXY_PID 2>/dev/null; then
        echo "Stopping SOCKS5 proxy (PID: $PROXY_PID)..."
        kill $PROXY_PID
    fi
    if [ ! -z "$PORT_FORWARD_PID" ] && kill -0 $PORT_FORWARD_PID 2>/dev/null; then
        echo "Stopping kubectl port-forward (PID: $PORT_FORWARD_PID)..."
        kill $PORT_FORWARD_PID
    fi
    echo "✓ Cleanup complete"
    exit 0
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Unset proxy for gcloud commands (to avoid connection issues)
unset HTTP_PROXY
unset HTTPS_PROXY
unset http_proxy
unset https_proxy

echo "=========================================="
echo "Local Development Proxy Setup"
echo "=========================================="
echo ""

# 1. Setup SOCKS5 proxy
echo "[1/2] Setting up SOCKS5 proxy for MSQP..."
echo ""
echo "Finding bastion server..."
BASTION_NAME=$(gcloud compute instances list --project ${PROJECT_ID} \
  --filter="name~'zoolake.*bastion-[0-9a-z]{4}$'" \
  --format="get(name)" | head -1)

if [ -z "$BASTION_NAME" ]; then
  echo "Error: Bastion server not found"
  exit 1
fi

echo "Bastion server: $BASTION_NAME"
echo "Starting SSH tunnel (localhost:1080)..."

# Start SOCKS5 proxy in background (without proxy)
gcloud compute ssh ${BASTION_NAME} \
  --project ${PROJECT_ID} \
  --tunnel-through-iap \
  -- -D 1080 -N &

PROXY_PID=$!

# Wait for proxy to be ready
sleep 2

# Export proxy environment variables (after proxy starts)
export HTTP_PROXY=socks5h://localhost:1080
export HTTPS_PROXY=socks5h://localhost:1080

echo "✓ SOCKS5 proxy is running (PID: $PROXY_PID)"
echo ""

# 2. Setup kubectl port-forward for ISP
echo "[2/2] Setting up kubectl port-forward for ISP..."
echo ""
echo "Starting port-forward to $ISP_SERVICE (localhost:$ISP_PORT)..."

# Temporarily unset proxy for kubectl (it needs direct access to k8s API)
(
    unset HTTP_PROXY
    unset HTTPS_PROXY
    unset http_proxy
    unset https_proxy
    kubectl port-forward -n $ISP_NAMESPACE svc/$ISP_SERVICE $ISP_PORT:$ISP_PORT
) &

PORT_FORWARD_PID=$!

# Wait for port-forward to be ready
sleep 2

echo "✓ kubectl port-forward is running (PID: $PORT_FORWARD_PID)"
echo ""

# Summary
echo "=========================================="
echo "✓ All services ready"
echo "=========================================="
echo ""
echo "Services:"
echo "  1. SOCKS5 Proxy:        localhost:1080 (PID: $PROXY_PID)"
echo "  2. ISP API:             localhost:$ISP_PORT (PID: $PORT_FORWARD_PID)"
echo ""
echo "Environment variables set:"
echo "  HTTP_PROXY=$HTTP_PROXY"
echo "  HTTPS_PROXY=$HTTPS_PROXY"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for background processes
wait
