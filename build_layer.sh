#!/usr/bin/env bash
# Build Lambda layer: install lambda/requirements.txt into lambda_layer/python for CDK asset.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
rm -rf lambda_layer
mkdir -p lambda_layer/python
python3 -m pip install -r lambda/requirements.txt -t lambda_layer/python --cache-dir ~/.pip_cache
echo "Built lambda_layer at $SCRIPT_DIR/lambda_layer"
