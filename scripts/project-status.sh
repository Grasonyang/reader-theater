#!/usr/bin/env bash
# 把 issue 或 PR 加進 org Project「開發看板」並設定欄位（可重複執行）。
# 用法：scripts/project-status.sh <issue 或 PR 的 URL> [欄位=值]...
# 例：  scripts/project-status.sh https://github.com/Yang-Home-99/research/issues/3 Status="In progress" Priority=P1 Size=S Sprint="Sprint 1"
# 欄位：Status、Priority、Size、Sprint（值必須與看板上的選項名稱完全相同）
set -euo pipefail

OWNER="Yang-Home-99"
NUMBER=1

[ $# -ge 1 ] || { sed -n '2,6p' "$0"; exit 1; }
url="$1"; shift

meta=$(gh api graphql -f query='
query($o:String!,$n:Int!){organization(login:$o){projectV2(number:$n){id fields(first:50){nodes{
  ... on ProjectV2SingleSelectField{id name options{id name}}
  ... on ProjectV2IterationField{id name configuration{iterations{id title}}}
}}}}}' -f o="$OWNER" -F n="$NUMBER")

project_id=$(jq -r '.data.organization.projectV2.id' <<<"$meta")
item_id=$(gh project item-add "$NUMBER" --owner "$OWNER" --url "$url" --format json --jq .id)
echo "item: $item_id"

for kv in "$@"; do
  name="${kv%%=*}"; value="${kv#*=}"
  field_id=$(jq -r --arg n "$name" '.data.organization.projectV2.fields.nodes[]|select(.name==$n)|.id' <<<"$meta")
  [ -n "$field_id" ] || { echo "找不到欄位：$name" >&2; exit 1; }
  if [ "$name" = "Sprint" ]; then
    opt=$(jq -r --arg n "$name" --arg v "$value" '.data.organization.projectV2.fields.nodes[]|select(.name==$n)|.configuration.iterations[]|select(.title==$v)|.id' <<<"$meta")
    [ -n "$opt" ] || { echo "找不到 Sprint：$value" >&2; exit 1; }
    gh project item-edit --id "$item_id" --project-id "$project_id" --field-id "$field_id" --iteration-id "$opt" >/dev/null
  else
    opt=$(jq -r --arg n "$name" --arg v "$value" '.data.organization.projectV2.fields.nodes[]|select(.name==$n)|.options[]|select(.name==$v)|.id' <<<"$meta")
    [ -n "$opt" ] || { echo "找不到 $name 的選項：$value" >&2; exit 1; }
    gh project item-edit --id "$item_id" --project-id "$project_id" --field-id "$field_id" --single-select-option-id "$opt" >/dev/null
  fi
  echo "$name = $value"
done
