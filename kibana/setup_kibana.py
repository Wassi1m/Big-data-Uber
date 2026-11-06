#!/usr/bin/env python3
"""
Uber Tunis — crée dans Kibana : data views + graphiques + carte + dashboard.

    python kibana/setup_kibana.py          # crée le dashboard s'il n'existe pas encore
    python kibana/setup_kibana.py --force  # le recrée (écrase les modifs faites dessus)
"""
import json, os, sys, time, uuid, urllib.request, urllib.error

ES, KB = "http://localhost:9200", "http://localhost:5601"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dashboard_uber.ndjson")
DASH_ID, MAP_ID = "uber-dashboard", "uber-map"
TS = "@timestamp"

# data view id -> index
DV = {
    "dv-taxis-live": "taxi-locations-live",
    "dv-taxis-history": "taxi-locations-history",
    "dv-clients-live": "client-requests-live",
    "dv-clients-history": "client-requests-history",
    "dv-zones": "zone-stats",
}


# ------------------------------------------------------------------ HTTP
def http(method, url, body=None, raw=False):
    h = {"kbn-xsrf": "true", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return r.status, (txt if raw else (json.loads(txt) if txt else {}))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_for(name, url, ok):
    print(f"⏳ Attente de {name}...", end="", flush=True)
    for _ in range(90):
        try:
            s, r = http("GET", url)
            if s == 200 and ok(r):
                print(" OK")
                return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(4)
    sys.exit(f"\n❌ {name} ne répond pas. Vérifie : docker compose ps")


# ------------------------------------------------------------------ Lens
def c_count(label="Nombre"):
    return {"label": label, "dataType": "number", "operationType": "count", "isBucketed": False,
            "scale": "ratio", "sourceField": "___records___", "customLabel": True}


def c_num(op, field, label):
    return {"label": label, "dataType": "number", "operationType": op, "isBucketed": False,
            "scale": "ratio", "sourceField": field, "customLabel": True}


def c_date():
    return {"label": "Temps", "dataType": "date", "operationType": "date_histogram",
            "sourceField": TS, "isBucketed": True, "scale": "interval",
            "params": {"interval": "auto", "includeEmptyRows": True, "dropPartials": False}}


def c_terms(field, order_col, size=10, label=None):
    return {"label": label or field, "dataType": "string", "operationType": "terms",
            "sourceField": field, "isBucketed": True, "scale": "ordinal", "customLabel": True,
            "params": {"size": size, "orderBy": {"type": "column", "columnId": order_col},
                       "orderDirection": "desc", "otherBucket": True, "missingBucket": False,
                       "parentFormat": {"id": "terms"}}}


def lens(oid, title, dv, vtype, cols, order, vis):
    return {"id": oid, "type": "lens", "attributes": {
        "title": title, "description": "", "visualizationType": vtype,
        "state": {"datasourceStates": {"formBased": {"layers": {"layer1": {
            "columns": cols, "columnOrder": order, "incompleteColumns": {}}}}},
            "visualization": vis, "query": {"query": "", "language": "kuery"},
            "filters": [], "adHocDataViews": {}, "internalReferences": []}},
        "references": [{"type": "index-pattern", "id": dv,
                        "name": "indexpattern-datasource-layer-layer1"}]}


def metric(oid, title, dv, col):
    return lens(oid, title, dv, "lnsMetric", {"m": col}, ["m"],
                {"layerId": "layer1", "layerType": "data", "metricAccessor": "m"})


def xy(oid, title, dv, x, ys, series="line", split=None):
    cols, order = {"x": x}, ["x"]
    if split:
        cols["s"], order = split, order + ["s"]
    acc = []
    for i, y in enumerate(ys):
        cols[f"y{i}"] = y
        order.append(f"y{i}")
        acc.append(f"y{i}")
    layer = {"layerId": "layer1", "layerType": "data", "seriesType": series,
             "xAccessor": "x", "accessors": acc}
    if split:
        layer["splitAccessor"] = "s"
    return lens(oid, title, dv, "lnsXY", cols, order, {
        "preferredSeriesType": series, "layers": [layer],
        "legend": {"isVisible": True, "position": "bottom"},
        "valueLabels": "hide", "fittingFunction": "Linear"})


def pie(oid, title, dv, field):
    return lens(oid, title, dv, "lnsPie", {"g": c_terms(field, "c", 8), "c": c_count()},
                ["g", "c"], {"shape": "donut", "layers": [{
                    "layerId": "layer1", "layerType": "data", "primaryGroups": ["g"],
                    "metrics": ["c"], "numberDisplay": "percent", "categoryDisplay": "default",
                    "legendDisplay": "default", "nestedLegend": False}]})


# ------------------------------------------------------------------ Carte
def vstyle(status_field=None, color="#54B399", size=7, icon="circle"):
    props = {
        "fillColor": {"type": "STATIC", "options": {"color": color}},
        "lineColor": {"type": "STATIC", "options": {"color": "#FFFFFF"}},
        "lineWidth": {"type": "STATIC", "options": {"size": 1}},
        "iconSize": {"type": "STATIC", "options": {"size": size}},
        "symbolizeAs": {"options": {"value": "icon" if icon != "circle" else "circle"}},
        "icon": {"type": "STATIC", "options": {"value": icon if icon != "circle" else "marker"}},
    }
    if status_field:
        props["fillColor"] = {"type": "DYNAMIC", "options": {
            "field": {"name": status_field, "origin": "source"}, "colorCategory": "palette_0",
            "type": "CATEGORICAL", "useCustomColorPalette": False}}
    return {"type": "VECTOR", "isTimeAware": True, "properties": props}


def es_layer(lid, label, ref, geo, tooltips, style, visible=True):
    return {"id": lid, "label": label, "type": "GEOJSON_VECTOR", "visible": visible,
            "alpha": 0.9, "minZoom": 0, "maxZoom": 24, "includeInFitToBounds": True,
            "joins": [], "style": style,
            "sourceDescriptor": {"type": "ES_SEARCH", "id": str(uuid.uuid4()), "geoField": geo,
                                 "scalingType": "LIMIT", "sortField": TS, "sortOrder": "desc",
                                 "tooltipProperties": tooltips, "indexPatternRefName": ref,
                                 "applyGlobalQuery": True, "applyGlobalTime": True,
                                 "applyForceRefresh": True, "filterByMapBounds": True}}


def build_map():
    layers = [
        {"id": "basemap", "label": "Fond de carte", "type": "EMS_VECTOR_TILE", "visible": True,
         "alpha": 1, "minZoom": 0, "maxZoom": 24, "includeInFitToBounds": True,
         "sourceDescriptor": {"type": "EMS_TMS", "isAutoSelect": True,
                              "lightModeDefault": "road_map_desaturated"},
         "style": {"type": "EMS_VECTOR_TILE", "color": ""}},
        {"id": "heat", "label": "Densité des taxis (historique)", "type": "HEATMAP",
         "visible": False, "alpha": 0.75, "minZoom": 0, "maxZoom": 24, "includeInFitToBounds": True,
         "style": {"type": "HEATMAP", "colorRampName": "theclassic"},
         "sourceDescriptor": {"type": "ES_GEO_GRID", "id": str(uuid.uuid4()), "geoField": "location",
                              "requestType": "heatmap", "resolution": "COARSE",
                              "metrics": [{"type": "count"}], "indexPatternRefName": "layer_3_source_index_pattern",
                              "applyGlobalQuery": True, "applyGlobalTime": True, "applyForceRefresh": True}},
        es_layer("clients", "Clients (point de prise en charge)", "layer_2_source_index_pattern",
                 "pickup_location", ["client_id", "status", "zone", "trip_km", "taxi_id"],
                 vstyle(color="#E7664C", size=6)),
        es_layer("taxis", "Taxis (position actuelle)", "layer_1_source_index_pattern",
                 "location", ["taxi_id", "driver", "status", "speed_kmh", "zone", "client_id"],
                 vstyle(status_field="status", size=8)),
    ]
    state = {"zoom": 11, "center": {"lon": 10.18, "lat": 36.81},
             "timeFilters": {"from": "now-15m", "to": "now"},
             "refreshConfig": {"isPaused": False, "interval": 5000},
             "query": {"query": "", "language": "kuery"}, "filters": [],
             "settings": {"autoFitToDataBounds": False}}
    return {"id": MAP_ID, "type": "map", "attributes": {
        "title": "Uber Tunis — Carte temps réel", "description": "",
        "layerListJSON": json.dumps(layers), "mapStateJSON": json.dumps(state),
        "uiStateJSON": json.dumps({"isLayerTOCOpen": True, "openTOCDetails": []})},
        "references": [
            {"name": "layer_1_source_index_pattern", "type": "index-pattern", "id": "dv-taxis-live"},
            {"name": "layer_2_source_index_pattern", "type": "index-pattern", "id": "dv-clients-live"},
            {"name": "layer_3_source_index_pattern", "type": "index-pattern", "id": "dv-taxis-history"}]}


# ------------------------------------------------------------------ Dashboard
def build():
    objs = [{"id": i, "type": "index-pattern",
             "attributes": {"title": idx, "name": idx, "timeFieldName": TS}, "references": []}
            for i, idx in DV.items()]

    # (objet, x, y, w, h)  — grille de 48 colonnes
    P = [
        (metric("uber-kpi-taxis", "Taxis actifs", "dv-taxis-live",
                c_num("unique_count", "taxi_id", "Taxis actifs")), 0, 0, 12, 7),
        (metric("uber-kpi-clients", "Demandes clients en cours", "dv-clients-live",
                c_num("unique_count", "client_id", "Clients")), 12, 0, 12, 7),
        (metric("uber-kpi-speed", "Vitesse moyenne (km/h)", "dv-taxis-live",
                c_num("average", "speed_kmh", "Vitesse moyenne km/h")), 24, 0, 12, 7),
        (metric("uber-kpi-trip", "Distance moyenne d'une course (km)", "dv-clients-history",
                c_num("average", "trip_km", "Distance moyenne km")), 36, 0, 12, 7),

        (build_map(), 0, 7, 32, 26),
        (pie("uber-pie-taxis", "Statut des taxis", "dv-taxis-live", "status"), 32, 7, 16, 13),
        (pie("uber-pie-clients", "Statut des demandes", "dv-clients-live", "status"), 32, 20, 16, 13),

        (xy("uber-requests-time", "Demandes clients dans le temps", "dv-clients-history",
            c_date(), [c_count("Demandes")], "bar_stacked", c_terms("status", "y0", 5, "Statut")),
         0, 33, 24, 14),
        (xy("uber-speed-time", "Vitesse moyenne des taxis dans le temps", "dv-taxis-history",
            c_date(), [c_num("average", "speed_kmh", "Vitesse moyenne km/h")], "line"),
         24, 33, 24, 14),

        (xy("uber-zone-taxis", "Taxis disponibles / occupés par zone", "dv-zones",
            c_terms("zone", "y0", 15, "Zone"),
            [c_num("average", "taxis_available", "Disponibles"),
             c_num("average", "taxis_busy", "Occupés")], "bar"), 0, 47, 24, 15),
        (xy("uber-zone-waiting", "Clients en attente par zone", "dv-zones",
            c_terms("zone", "y0", 15, "Zone"),
            [c_num("average", "clients_waiting", "Clients en attente")], "bar_horizontal"),
         24, 47, 24, 15),

        (xy("uber-zone-requests", "Zones les plus demandées", "dv-clients-history",
            c_terms("zone", "y0", 10, "Zone"), [c_count("Demandes")], "bar_horizontal"),
         0, 62, 24, 14),
        (xy("uber-zone-trips", "Courses terminées / annulées par zone", "dv-zones",
            c_terms("zone", "y0", 15, "Zone"),
            [c_num("max", "trips_completed", "Terminées"),
             c_num("max", "trips_cancelled", "Annulées")], "bar_stacked"), 24, 62, 24, 14),
    ]

    panels, refs = [], []
    for n, (o, x, y, w, h) in enumerate(P, 1):
        objs.append(o)
        pid = str(n)
        panels.append({"type": o["type"], "panelIndex": pid, "panelRefName": f"panel_{pid}",
                       "gridData": {"x": x, "y": y, "w": w, "h": h, "i": pid},
                       "embeddableConfig": {"enhancements": {}}})
        refs.append({"name": f"{pid}:panel_{pid}", "type": o["type"], "id": o["id"]})

    objs.append({"id": DASH_ID, "type": "dashboard", "attributes": {
        "title": "Uber Tunis — Suivi temps réel", "description": "Généré par setup_kibana.py",
        "panelsJSON": json.dumps(panels),
        "optionsJSON": json.dumps({"useMargins": True, "syncColors": True, "syncCursor": True,
                                   "syncTooltips": False, "hidePanelTitles": False}),
        "timeRestore": True, "timeFrom": "now-15m", "timeTo": "now",
        "refreshInterval": {"pause": False, "value": 5000},
        "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
            {"query": {"query": "", "language": "kuery"}, "filter": []})}},
        "references": refs})
    return objs


# ------------------------------------------------------------------ Main
def main():
    force = "--force" in sys.argv
    wait_for("Elasticsearch", ES, lambda r: "version" in r)
    wait_for("Kibana", f"{KB}/api/status",
             lambda r: r.get("status", {}).get("overall", {}).get("level") == "available")

    if not force and http("GET", f"{KB}/api/saved_objects/dashboard/{DASH_ID}")[0] == 200:
        print("ℹ️  Le dashboard existe déjà (tes modifs sont conservées). "
              "Pour le recréer : python kibana/setup_kibana.py --force")
    else:
        missing = [i for i in DV.values() if http("HEAD", f"{ES}/{i}")[0] != 200]
        if missing:
            print("⚠️  Index absents (les graphes liés seront vides) :", ", ".join(missing))
        ok, ko = 0, 0
        for o in build():
            s, r = http("POST", f"{KB}/api/saved_objects/{o['type']}/{o['id']}?overwrite=true",
                        {"attributes": o["attributes"], "references": o["references"]})
            if s == 200:
                ok += 1
            else:
                ko += 1
                print(f"❌ {o['type']} '{o['attributes']['title']}' : {str(r)[:300]}")
        print(f"✅ {ok} objets créés" + (f", {ko} en erreur" if ko else ""))

    # Sauvegarde (format exporté par Kibana, réimportable)
    s, r = http("POST", f"{KB}/api/saved_objects/_export",
                {"objects": [{"type": "dashboard", "id": DASH_ID}],
                 "includeReferencesDeep": True}, raw=True)
    if s == 200:
        open(OUT, "w").write(r)
        print(f"💾 Sauvegarde : {OUT}")
    print(f"\n👉 Dashboard : {KB}/app/dashboards#/view/{DASH_ID}")
    print(f"👉 Carte     : {KB}/app/maps/map/{MAP_ID}")


if __name__ == "__main__":
    main()
