#!/bin/bash
# Restaure une sauvegarde Kibana. Usage : ./kibana/restore.sh [fichier.ndjson]
cd "$(dirname "$0")/.." || exit 1
FILE="${1:-kibana/backups/latest.ndjson}"
[ -f "$FILE" ] || { echo "❌ Fichier introuvable : $FILE"; exit 1; }
curl -s -X POST "http://localhost:5601/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" --form file=@"$FILE"
echo; echo "✅ Restauré depuis $FILE"
