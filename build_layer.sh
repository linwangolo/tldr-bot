#!/usr/bin/env bash
# Build Lambda layer: install lambda/requirements.txt into lambda_layer/python for CDK asset.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
rm -rf lambda_layer
mkdir -p lambda_layer/python
uv pip install -r lambda/requirements.txt -t lambda_layer/python
echo "Built lambda_layer at $SCRIPT_DIR/lambda_layer"
