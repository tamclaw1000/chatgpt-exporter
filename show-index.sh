#!/usr/bin/env bash
set -euo pipefail

INDEX="export/mwt/conversations/index.json"

jq -r '.[] | [(.create_time // .update_time // ""), (.title // "(untitled)")] | @tsv' "$INDEX" \
  | sort -r \
  | TZ=UTC gawk -F'\t' '
      {
        ts = $1
        if (ts == "") { printf "\t%s\n", $2; next }
        sub(/\.?[0-9]*Z$/, "", ts)
        split(ts, a, /[-T:]/)
        epoch = mktime(a[1] " " a[2] " " a[3] " " a[4] " " a[5] " " a[6])
        printf "%d\t%s\n", epoch, $2
      }' \
  | TZ=America/Chicago gawk -F'\t' '
      {
        if ($1 == "") { printf "  %s\n", $2; next }
        printf "%s  %s\n", strftime("%Y-%m-%d %H:%M", $1 + 0), $2
      }'
