#!/bin/bash
# Lance tout le projet Uber Tunis : Docker + dashboards Kibana + simulateur
cd "$(dirname "$0")" || exit 1

echo "🐳 Démarrage des conteneurs..."
sudo sysctl -q -w vm.max_map_count=262144
docker compose up -d || exit 1

source venv/bin/activate
pip install -q kafka-python 2>/dev/null

echo "🚕 Démarrage du simulateur (logs : simulator.log)..."
pkill -f simulator/simulator.py 2>/dev/null
nohup python simulator/simulator.py > simulator.log 2>&1 &
echo "   PID $!"

echo "⏳ 40 s pour laisser arriver les premières données..."
sleep 40

if [ -f kibana/backups/latest.ndjson ]; then
  echo "♻️  Restauration de ta dernière sauvegarde..."
  ./kibana/restore.sh > /dev/null
fi
python kibana/setup_kibana.py

echo
echo "Kafka UI : http://localhost:8085"
echo "Kibana   : http://localhost:5601/app/dashboards#/view/uber-dashboard"
echo "Jupyter  : http://localhost:8888  (token admin)"
echo "Arrêt    : ./stop.sh"
