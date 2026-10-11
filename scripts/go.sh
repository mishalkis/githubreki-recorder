#!/bin/bash
# usage: go.sh slug  -> диспатч, ожидание, скачивание в runs/<id>/out; печатает id
cd /home/myuser/githubreki-recorder
slug=$1
gh workflow run record.yml -f demo=$slug >/dev/null || exit 1
sleep 12
id=$(gh run list --workflow record.yml -L 10 --json databaseId,displayTitle,createdAt --jq "[.[]|select(.displayTitle==\"record $slug\")]|sort_by(.createdAt)|last|.databaseId")
echo "run $id" >&2
gh run watch $id --exit-status >/dev/null 2>&1
echo "result: $(gh run view $id --json conclusion --jq .conclusion)" >&2
mkdir -p runs/$id/out && gh run download $id -n out -D runs/$id/out >/dev/null 2>&1
echo $id
