#!/bin/bash
set -euxo pipefail
mkdir -p /testbed
cp -r /local_repo/. /testbed/
chmod -R 777 /testbed
cd /testbed
git reset --hard 7269fa3e33e8d02485a647da91a5a2a60a06af61
git remote remove origin || true
git tag -l | while read tag; do git tag -d "$tag"; done || true
git reflog expire --expire=now --all || true
git gc --prune=now --aggressive || true
source /opt/miniconda3/bin/activate
conda activate testbed
echo "Current environment: $CONDA_DEFAULT_ENV"
sed -i 's/requires = \["setuptools",/requires = \["setuptools==68.0.0",/' pyproject.toml
python -m pip install -e .[test] --verbose
git config --global user.email setup@swebench.config
git config --global user.name SWE-bench
git commit --allow-empty -am SWE-bench
