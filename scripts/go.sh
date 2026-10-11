#!/bin/bash
# usage: go.sh slug  -> диспатч, ожидание, скачивание в runs/<id>/out; печатает id (только gh api, редкий опрос)
cd /home/myuser/githubreki-recorder
R=repos/mishalkis/githubreki-recorder
slug=$1
gh workflow run record.yml -f demo=$slug >/dev/null || exit 1
sleep 15
id=$(gh api "$R/actions/runs?per_page=20&event=workflow_dispatch" --jq "[.workflow_runs[]|select(.display_title==\"record $slug\")]|sort_by(.created_at)|last|.id")
echo "run $id" >&2
while :; do
  st=$(gh api $R/actions/runs/$id --jq '.status+" "+(.conclusion//"")')
  case "$st" in completed*) break;; esac
  sleep 30
done
echo "result: ${st#completed }" >&2
mkdir -p runs/$id/out
aid=$(gh api $R/actions/runs/$id/artifacts --jq '.artifacts[0].id')
gh api $R/actions/artifacts/$aid/zip > /tmp/art_$id.zip && unzip -qo /tmp/art_$id.zip -d runs/$id/out && rm /tmp/art_$id.zip
echo $id
