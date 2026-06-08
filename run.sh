#!/bin/bash
set -e

ACCOUNT="mwt"

if [ $# -eq 0 ]; then
    echo "Usage:"
    echo "  $0 refresh"
    echo "  $0 list-projects"
    echo "  $0 update-projects <project_id>"
    exit 1
fi

MODE="$1"
PROJECT_ID="$2"

export CHATGPT_TOKEN=$(pass show openai/manweitam/access_token)

npm run build

case "$MODE" in
  refresh)
    rm -f "export/${ACCOUNT}/conversations/listing-cache.json"

    npm start -- backup \
      --output "export/${ACCOUNT}" \
      --incremental \
      --download-files \
      --verbose \
      --concurrency 3 \
      --delay 1000
    ;;

  list-projects)
    mkdir -p "export/${ACCOUNT}/projects"

    npm start -- projects | tee "export/${ACCOUNT}/projects/projects-list.txt"
    ;;

  update-projects)
    if [ -z "$PROJECT_ID" ]; then
      echo "Usage: $0 update-projects <project_id>"
      exit 1
    fi

    npm start -- backup \
      --output "export/${ACCOUNT}" \
      --project "$PROJECT_ID" \
      --download-files \
      --verbose \
      --concurrency 1 \
      --delay 500
    ;;

  *)
    echo "Unknown mode: $MODE"
    echo
    echo "Usage:"
    echo "  $0 refresh"
    echo "  $0 list-projects"
    echo "  $0 update-projects <project_id>"
    exit 1
    ;;
esac

echo Files Changed:
find export/${ACCOUNT} -cmin -5

rsync -ruvh --exclude .git --progress . /mnt/nas5/systems/takeouts/OpenAI/export

cd export
git add .
git commit -m "Backup $(date)"
git log -1 --name-status



unset CHATGPT_TOKEN
