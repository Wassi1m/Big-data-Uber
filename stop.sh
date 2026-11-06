#!/bin/bash
# Sauvegarde Kibana puis arrête tout (SANS effacer les données)
cd "$(dirname "$0")" || exit 1
./kibana/backup.sh
pkill -f simulator/simulator.py 2>/dev/null && echo "🛑 Simulateur arrêté"
docker compose stop
echo "✅ Arrêté. Ne fais jamais 'docker compose down -v' (ça efface les données)."
