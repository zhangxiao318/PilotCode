#!/bin/bash
set -euxo pipefail
mkdir -p /testbed
cp -r /local_repo/. /testbed/
chmod -R 777 /testbed
cd /testbed
git reset --hard df46b329e0900e9e4dc1d60816c1dce6dfc1094e
git remote remove origin || true
git tag -l | while read tag; do git tag -d "$tag"; done || true
git reflog expire --expire=now --all || true
git gc --prune=now --aggressive || true
source /opt/miniconda3/bin/activate
conda activate testbed
echo "Current environment: $CONDA_DEFAULT_ENV"
python -m pip install -e .
git config --global user.email setup@swebench.config
git config --global user.name SWE-bench
git commit --allow-empty -am SWE-bench
