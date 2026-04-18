#!/bin/bash
# Source this before running any PilotCode / SWE-bench commands:
#   source /home/zx/mycc/PilotCode/setup_cache_env.sh

# 1. HuggingFace 走国内镜像 + 固定缓存目录
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HOME="/home/zx/.cache/huggingface"
export HF_DATASETS_CACHE="/home/zx/.cache/huggingface/datasets"
export HUGGINGFACE_HUB_CACHE="/home/zx/.cache/huggingface/hub"

# 2. pip / conda 固定缓存目录（宿主机级复用）
export PIP_CACHE_DIR="/home/zx/.cache/pip"
export CONDA_PKGS_DIRS="/home/zx/.cache/conda/pkgs"

# 3. Docker BuildKit 启用（支持 RUN --mount=type=cache）
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 4. Git 本地仓库持久缓存目录
export SWE_BENCH_REPO_CACHE="/home/zx/.cache/swe-bench-repos"
mkdir -p "${SWE_BENCH_REPO_CACHE}"
mkdir -p "${PIP_CACHE_DIR}"
mkdir -p "${CONDA_PKGS_DIRS}"

echo "[CACHE] Environment configured."
echo "  HF_ENDPOINT=${HF_ENDPOINT}"
echo "  PIP_CACHE_DIR=${PIP_CACHE_DIR}"
echo "  CONDA_PKGS_DIRS=${CONDA_PKGS_DIRS}"
echo "  SWE_BENCH_REPO_CACHE=${SWE_BENCH_REPO_CACHE}"
