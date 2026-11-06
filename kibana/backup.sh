#!/bin/bash
# Sauvegarde TOUS les dashboards, cartes, graphiques et data views de Kibana
# (y compris ceux faits à la main) dans kibana/backups/
cd "$(dirname "$0")/.." || exit 1
mkdir -p kibana/backups
FILE="kibana/backups/kibana_$(date +%Y%m%d_%H%M%S).ndjson"
curl -s -X POST "http://localhost:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" -H "Content-Type: application/json" \
  -d '{"type":["dashboard","lens","map","visualization","search","index-pattern"],"includeReferencesDeep":true}' \
  -o "$FILE"
if [ -s "$FILE" ] && ! grep -q '"statusCode"' "$FILE"; then
  cp "$FILE" kibana/backups/latest.ndjson
  echo "✅ Sauvegarde : $FILE ($(wc -l < "$FILE") objets)"
else
  echo "❌ Échec (Kibana est-il démarré ?)"; cat "$FILE"; rm -f "$FILE"; exit 1
fi
