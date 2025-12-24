# app.py
import os
import sys
import logging
from threading import Lock
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
try:
    # pydantic v2 compatibility layer
    from pydantic.v1 import ValidationError
except ImportError:  # pragma: no cover
    from pydantic import ValidationError

from core.twin_service import DigitalTwinService
from core.schemas import Generate3DRequest
from core.schemas import MeshGenerationParams, Room2DInput
from core.cad_parser import DxfToMeshParser
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
        "endpoints": [
            "/api/v1/home_config",
            "/api/v1/sensor_event",
            "/api/v1/generate_3d",
            "/api/v1/auto_generate_from_dxf",
            "/api/v1/3d_model/<mesh_id>",
            "/api/v1/3d_model/latest?home_id=<home_id>",
        ],
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


@app.route('/api/v1/generate_3d', methods=['POST'])
def generate_3d():
    """接收 2D 平面圖資料並生成 3D mesh (vertices/faces)。"""
    payload = request.get_json(silent=True) or {}
    try:
        if hasattr(Generate3DRequest, "model_validate"):
            request_model = Generate3DRequest.model_validate(payload)
        else:
            request_model = Generate3DRequest.parse_obj(payload)
    except ValidationError as e:
        return jsonify({"error": "invalid payload", "details": e.errors()}), 400

    result, err = twin_service.generate_3d_model(request_model)
    if err:
        return jsonify({"error": err}), 400

    return jsonify({"message": "3d mesh generated", "result": result})


@app.route('/api/v1/auto_generate_from_dxf', methods=['POST'])
def auto_generate_from_dxf():
    """接收 DXF 檔並解析指定圖層為房間 polygon，再生成 3D mesh。"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    home_id = request.form.get("home_id") or "main_home_config"
    try:
        level = int(request.form.get("level", 1))
    except Exception:
        return jsonify({"error": "level must be integer"}), 400
    try:
        floor_height = float(request.form.get("height", 3.0))
    except Exception:
        return jsonify({"error": "height must be numeric"}), 400

    layers_raw = request.form.get("layers")
    layer_names = [s.strip() for s in layers_raw.split(",")] if layers_raw else ["WALL", "WALLS", "STRUCTURE"]

    parser = DxfToMeshParser(target_layer_names=layer_names)
    try:
        file_content = file.read()
        content_str = file_content.decode("utf-8", errors="ignore")
        dxf_payload = parser.parse(content_str, level=level, height=floor_height)
    except Exception as e:
        logger.exception("Error parsing DXF")
        return jsonify({"error": f"DXF parsing failed: {e}"}), 422

    if not dxf_payload.get("rooms"):
        return jsonify({"error": "DXF parsing produced no rooms"}), 422

    room_models = []
    for room in dxf_payload["rooms"]:
        room = dict(room)
        room.setdefault("openings", [])
        room.setdefault("walls", [])
        room.setdefault("holes", [])
        room.setdefault("level", level)
        room["z_offset"] = float(dxf_payload.get("z_offset", 0.0) or 0.0)
        try:
            if hasattr(Room2DInput, "model_validate"):
                room_model = Room2DInput.model_validate(room)
            else:
                room_model = Room2DInput.parse_obj(room)
        except ValidationError as e:
            return jsonify({"error": "invalid parsed room", "details": e.errors()}), 422
        room_models.append(room_model)

    params = MeshGenerationParams(wall_height=floor_height)
    metadata = {
        "original_image_url": getattr(file, "filename", None),
        "parsing_confidence": None,
        "pixel_to_meter_ratio": None,
        "level": level,
        "floor_id": dxf_payload.get("id"),
        "z_offset": dxf_payload.get("z_offset"),
        "source": "dxf_parser",
        "layers": layer_names,
    }

    request_model = Generate3DRequest(
        home_id=home_id,
        rooms=room_models,
        params=params,
        metadata=metadata,
    )

    result, twin_err = twin_service.generate_3d_model(request_model)
    if twin_err:
        return jsonify({"error": twin_err}), 400

    return jsonify({
        "message": "3D Model generated from DXF",
        "parsed_geometry": dxf_payload,
        "mesh_id": result["mesh_id"],
        "result": result,
    })


@app.route('/api/v1/3d_model/<mesh_id>', methods=['GET'])
def get_3d_model(mesh_id: str):
    """取得指定 mesh_id 的 3D mesh JSON。"""
    result, err = twin_service.get_3d_model(mesh_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify(result)


@app.route('/api/v1/3d_model/latest', methods=['GET'])
def get_latest_3d_model():
    """取得指定 home_id 最新生成的 3D mesh JSON。"""
    home_id = request.args.get("home_id")
    if not home_id:
        return jsonify({"error": "home_id is required"}), 400

    result, err = twin_service.get_latest_3d_model_for_home(home_id)
    if err:
        return jsonify({"error": err}), 404
    return jsonify(result)


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
