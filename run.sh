#!/bin/bash
export CHATGPT_TOKEN=$(pass show openai/manweitam/access_token)
ACCOUNT=mwt

npm run build

### Refresh
rm export/mwt/conversations/listing-cache.json
npm start -- backup \
--output "export/${ACCOUNT}" \
--incremental \
--download-files \
--verbose \
--concurrency 3 \
--delay 1000

exit -1
 
## List Projects
npm start -- projects | tee exports/${ACCOUNT}/projects/projects-list.txt

## Update Projects
# --for i in $(cut -c1-36 export/mwt/projects/projects-list.txt|grep -v ^x); do
# --  echo $i;
# --  npm start -- backup \
# --    --output "export/${ACCOUNT}" \
# --    --project $i
# --    --download-files \
# --    --verbose \
# --    --concurrency 1 \
# --    --delay 500
# --done
# --
# --exit -1
# --
unset CHATGPT_TOKEN

#npx chatgpt-exporter backup --token $CHATGPT_TOKEN --verbose --incremental --download-files --output "export/${ACCOUNT}"
