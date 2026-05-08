from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import time, math, random, requests

app = Flask(__name__)
CORS(app)

# Centre protégé par défaut : Beni
BASE_LAT = 0.4911
BASE_LON = 29.4731

tracked = {}

# Source ADS-B locale si dump1090 est installé
ADS_B_URL = "http://127.0.0.1:8080/data/aircraft.json"


def distance_m(lat1, lon1, lat2, lon2):
    R = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify(obj):
    d = distance_m(obj["lat"], obj["lon"], BASE_LAT, BASE_LON)

    if d < 800:
        return "danger", "Intrusion dans zone sensible"

    if obj["speed"] < 8:
        return "watch", "Objet lent ou stationnaire"

    return "normal", "RAS"





def get_adsb_objects():
    objects = []
    try:
        r = requests.get(ADS_B_URL, timeout=1.5)
        data = r.json()

        for a in data.get("aircraft", []):
            if "lat" not in a or "lon" not in a:
                continue

            objects.append({
                "id": (a.get("flight") or a.get("hex") or "ADS-B").strip(),
                "type": "Avion ADS-B réel",
                "lat": a["lat"],
                "lon": a["lon"],
                "speed": round(float(a.get("gs") or 0) * 1.852, 2),
                "altitude": int(a.get("alt_baro") or 0),
                "source": "ADS-B",
                "timestamp": time.time()
            })

    except Exception:
        pass

    return objects


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/tracker")
def tracker():
    return render_template("tracker.html")


@app.route("/api/update", methods=["POST"])
def update():
    data = request.json

    object_id = data.get("id", "PHONE-01")

    obj = {
        "id": object_id,
        "type": data.get("type", "Téléphone GPS autorisé"),
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "speed": round(float(data.get("speed", 0) or 0) * 3.6, 2),
        "altitude": round(float(data.get("altitude", 0) or 0), 2),
        "source": "GPS MOBILE",
        "timestamp": time.time()
    }

    status, alert = classify(obj)
    obj["status"] = status
    obj["alert"] = alert

    tracked[object_id] = obj

    return jsonify({"success": True, "object": obj})


@app.route("/api/objects")
def objects():
    now = time.time()

    active_gps = [
        o for o in tracked.values()
        if now - o["timestamp"] <= 60
    ]

    for obj in active_gps:
        status, alert = classify(obj)
        obj["status"] = status
        obj["alert"] = alert

    return jsonify({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(active_gps),
        "objects": active_gps
    })


@app.route("/api/stats")
def stats():
    data = objects().json["objects"]

    return jsonify({
        "total": len(data),
        "normal": len([o for o in data if o["status"] == "normal"]),
        "watch": len([o for o in data if o["status"] == "watch"]),
        "danger": len([o for o in data if o["status"] == "danger"]),
        "level": "ALERTE ROUGE" if any(o["status"] == "danger" for o in data) else "OPÉRATIONNEL"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)