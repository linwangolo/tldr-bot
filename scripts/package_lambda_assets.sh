#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT_DIR/infra/terraform"
BUILD_DIR="$TF_DIR/.build"
DIST_DIR="$TF_DIR/dist"

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR/lambda" "$BUILD_DIR/layer/python" "$DIST_DIR"

# Lambda function package
cp "$ROOT_DIR"/lambda/*.py "$BUILD_DIR/lambda/"
(
  cd "$BUILD_DIR/lambda"
  zip -qr "$DIST_DIR/lambda_function.zip" .
)

# Lambda layer package
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r "$ROOT_DIR/lambda/requirements.txt" -t "$BUILD_DIR/layer/python" >/dev/null
(
  cd "$BUILD_DIR/layer"
  zip -qr "$DIST_DIR/lambda_layer.zip" .
)

echo "Packaged:"
echo "  $DIST_DIR/lambda_function.zip"
echo "  $DIST_DIR/lambda_layer.zip"

