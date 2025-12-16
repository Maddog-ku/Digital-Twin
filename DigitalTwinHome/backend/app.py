# app.py
import os
import sys
import logging
from threading import Lock
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from core.twin_service import DigitalTwinService
from config import HOST, PORT

load_dotenv()

# --- 設置日誌 ---
logger = logging.getLogger('digital_twin_app')
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(console_handler)
logger.propagate = False

# --- Flask 和 SocketIO 設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret')  # 生產環境請覆寫
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# --- 數位孿生服務 ---
twin_service = DigitalTwinService(logger)
twin_service.initialize()

client_count = 0
client_lock = Lock()


# --- REST API 路由 ---
@app.route('/', methods=['GET'])
def index():
    """存活檢查與可用端點"""
    return jsonify({
        "message": "Digital Twin backend is running",
        "endpoints": ["/api/v1/home_config", "/api/v1/sensor_event"],
        "ws_namespace": "/twin",
        "ws_event": "sensor_update"
    })


@app.route('/api/v1/home_config', methods=['GET'])
def get_home_config():
    """返回完整的住家配置和當前狀態 (GET 請求)"""
    return jsonify(twin_service.get_full_config())


@app.route('/api/v1/sensor_event', methods=['POST'])
def handle_sensor_event():
    """接受外部感測器事件並更新數位孿生狀態"""
    payload = request.get_json(silent=True) or {}
    room_id = payload.get("room_id")
    sensor_id = payload.get("sensor_id")
    sensor_type = payload.get("type")
    new_status = payload.get("new_status") or payload.get("status")
    location = payload.get("location")

    if not all([room_id, sensor_id, sensor_type, new_status]):
        return jsonify({"error": "room_id, sensor_id, type, new_status are required"}), 400

    update_payload, err = twin_service.apply_sensor_event(
        room_id=room_id,
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        new_status=new_status,
        location=location
    )

    if err:
        return jsonify({"error": err}), 404

    return jsonify({"message": "sensor event applied", "update": update_payload})


# --- SocketIO 事件處理 ---
@socketio.on('connect', namespace='/twin')
def on_connect():
    """當客戶端連線時，啟動模擬執行緒"""
    global client_count
    logger.info('Client connected to /twin namespace. Starting data stream...')
    with client_lock:
        client_count += 1
        twin_service.start_simulation(socketio)


@socketio.on('disconnect', namespace='/twin')
def on_disconnect():
    """客戶端斷開連線時觸發"""
    global client_count
    logger.info('Client disconnected from /twin namespace.')
    with client_lock:
        client_count = max(0, client_count - 1)
        if client_count == 0:
            twin_service.stop_simulation()


# --- 應用啟動 ---
if __name__ == '__main__':
    try:
        logger.info(f"Flask/SocketIO Server running on http://{HOST}:{PORT}")
        socketio.run(app, host=HOST, port=PORT)
    except Exception as e:
        logger.exception("Error starting server")
        sys.exit(1)
