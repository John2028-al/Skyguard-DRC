from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time
import math

app = Flask(__name__)
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

BASE_LAT = 0.4911
BASE_LON = 29.4731

tracked = {}
tracker_sockets = {}
dashboard_sockets = set()


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
        "media_active": bool(data.get("media_active", False))
    }

    status, alert = classify(obj)
    obj["status"] = status
    obj["alert"] = alert

    tracked[object_id] = obj

    return jsonify({"success": True, "object": obj})


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
        obj["media_online"] = obj["id"] in tracker_sockets

    danger = len([o for o in active if o["status"] == "danger"])
    watch = len([o for o in active if o["status"] == "watch"])
    normal = len([o for o in active if o["status"] == "normal"])

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


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "SkyGuard-DRC"})


@socketio.on("register_tracker")
def register_tracker(data):
    object_id = data.get("id", "PHONE-01")
    tracker_sockets[object_id] = request.sid
    emit("tracker_registered", {"id": object_id, "sid": request.sid})


@socketio.on("register_dashboard")
def register_dashboard():
    dashboard_sockets.add(request.sid)
    emit("dashboard_registered", {"sid": request.sid})


@socketio.on("call_tracker")
def call_tracker(data):
    object_id = data.get("id")
    dashboard_sid = request.sid
    tracker_sid = tracker_sockets.get(object_id)

    if tracker_sid:
        socketio.emit("incoming_call", {
            "object_id": object_id,
            "dashboard_sid": dashboard_sid
        }, room=tracker_sid)
    else:
        emit("webrtc_error", {"message": "Tracker introuvable ou média non actif"})


@socketio.on("webrtc_offer")
def webrtc_offer(data):
    socketio.emit("webrtc_offer", data, room=data["to"])


@socketio.on("webrtc_answer")
def webrtc_answer(data):
    socketio.emit("webrtc_answer", data, room=data["to"])


@socketio.on("webrtc_ice")
def webrtc_ice(data):
    socketio.emit("webrtc_ice", data, room=data["to"])


@socketio.on("disconnect")
def disconnect():
    sid = request.sid

    dashboard_sockets.discard(sid)

    for object_id, tracker_sid in list(tracker_sockets.items()):
        if tracker_sid == sid:
            del tracker_sockets[object_id]


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)