from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import time
import math

app = Flask(__name__)
CORS(app)

BASE_LAT = 0.4911
BASE_LON = 29.4731

tracked = {}


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

    if obj.get("speed", 0) < 8:
        return "watch", "Objet lent ou stationnaire"

    return "normal", "RAS"


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/tracker")
def tracker():
    return render_template("tracker.html")


@app.route("/api/update", methods=["POST"])
def update():
    data = request.json or {}

    try:
        object_id = data.get("id", "PHONE-01")

        obj = {
            "id": object_id,
            "type": data.get("type", "Téléphone GPS autorisé"),
            "lat": float(data["lat"]),
            "lon": float(data["lon"]),
            "speed": round(float(data.get("speed", 0) or 0) * 3.6, 2),
            "altitude": round(float(data.get("altitude", 0) or 0), 2),
            "accuracy": round(float(data.get("accuracy", 0) or 0), 2),
            "source": "GPS MOBILE",
            "timestamp": time.time(),
            "timestamp_mobile": data.get("timestamp_mobile", ""),
            "media_peer_id": data.get("media_peer_id", ""),
            "media_active": bool(data.get("media_active", False))
        }

        status, alert = classify(obj)
        obj["status"] = status
        obj["alert"] = alert

        tracked[object_id] = obj

        return jsonify({
            "success": True,
            "object": obj
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/api/objects")
def objects():
    now = time.time()

    active = [
        o for o in tracked.values()
        if now - o["timestamp"] <= 90
    ]

    for obj in active:
        status, alert = classify(obj)
        obj["status"] = status
        obj["alert"] = alert
        obj["age_seconds"] = round(now - obj["timestamp"], 1)

    normal = len([o for o in active if o["status"] == "normal"])
    watch = len([o for o in active if o["status"] == "watch"])
    danger = len([o for o in active if o["status"] == "danger"])

    return jsonify({
        "success": True,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(active),
        "normal": normal,
        "watch": watch,
        "danger": danger,
        "level": "ALERTE ROUGE" if danger > 0 else "OPÉRATIONNEL",
        "objects": active
    })


@app.route("/api/stats")
def stats():
    now = time.time()

    active = [
        o for o in tracked.values()
        if now - o["timestamp"] <= 90
    ]

    return jsonify({
        "success": True,
        "total": len(active),
        "normal": len([o for o in active if o["status"] == "normal"]),
        "watch": len([o for o in active if o["status"] == "watch"]),
        "danger": len([o for o in active if o["status"] == "danger"]),
        "level": "ALERTE ROUGE" if any(o["status"] == "danger" for o in active) else "OPÉRATIONNEL"
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "SkyGuard-DRC",
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)