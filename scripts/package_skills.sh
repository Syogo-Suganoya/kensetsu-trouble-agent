#!/usr/bin/env bash
# Claude.ai（設定 > 機能 > スキル）にアップロードするため、各Skillをzip化する。
# 出力: dist/<skill-name>.zip
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p dist

for dir in .claude/skills/*/; do
  name="$(basename "$dir")"
  rm -f "dist/${name}.zip"
  (cd .claude/skills && zip -qr "../../dist/${name}.zip" "$name" -x '*.DS_Store')
  echo "dist/${name}.zip"
done
