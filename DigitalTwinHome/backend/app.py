# app.py
import os
import sys
import logging
from threading import Lock
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_socketio import SocketIO
import cv2
import numpy as np
try:
    # pydantic v2 compatibility layer
    from pydantic.v1 import ValidationError
except ImportError:  # pragma: no cover
    from pydantic import ValidationError

from core.twin_service import DigitalTwinService
from core.schemas import Generate3DRequest
from core.schemas import MeshGenerationParams, Room2DInput
from core.image_processor import parse_single_floor_image
from core.floorplan_parser import FloorplanToMeshParser
from core.cad_parser import DxfToMeshParser
from config import HOST, PORT

load_dotenv()

# --- AI 解析服務 (Placeholder/MVP) ---
class AI_Perception_Service:
    """將上傳影像解析為 2D 幾何 JSON（基於 OpenCV 的 MVP 版）。"""

    @staticmethod
    def _safe_float(value):
        try:
            f = float(value)
            if f <= 0:
                return None
            return f
        except Exception:
            return None

    @staticmethod
    def parse_image(image_file, pixel_to_meter_ratio=None):
        """
        回傳 (geometry_json, error)。輸出符合 Generate3DRequest。

        解析流程：
        1) 讀取影像並二值化
        2) 輪廓檢測 + 多邊形簡化
        3) 座標依 pixel_to_meter_ratio 轉公尺並平移到原點
        """
        try:
            filename = getattr(image_file, "filename", "upload.png")
            file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
            image_file.seek(0)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if img is None:
                return None, "Failed to decode image"

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                return None, "No closed contours detected"

            largest = max(contours, key=cv2.contourArea)
            peri = cv2.arcLength(largest, True)
            epsilon = 0.01 * peri
            approx = cv2.approxPolyDP(largest, epsilon, True)
            pts = approx.reshape(-1, 2).tolist()
            if len(pts) < 3:
                x, y, w, h = cv2.boundingRect(largest)
                pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

            scale = pixel_to_meter_ratio or 0.01  # fallback: 1px = 1cm
            scaled = [[float(x) * scale, float(y) * scale] for x, y in pts]
            xs = [p[0] for p in scaled]
            ys = [p[1] for p in scaled]
            min_x, min_y = min(xs), min(ys)
            polygon = [[x - min_x, y - min_y] for x, y in scaled]

            area_px = cv2.contourArea(largest)
            img_area = img.shape[0] * img.shape[1]
            confidence = max(0.1, min(0.95, area_px / float(img_area + 1e-6)))

            geometry_json = {
                "home_id": "main_home_config",
                "rooms": [
                    {
                        "id": "auto_room_1",
                        "name": "AI Parsed Room",
                        "polygon": polygon,
                        "openings": [],
                    }
                ],
                "params": {"wall_height": 2.8, "wall_thickness": 0.12, "use_csg": True},
                "metadata": {
                    "source": "opencv_contour",
                    "original_image_url": filename,
                    "parsing_confidence": confidence,
                    "pixel_to_meter_ratio": scale,
                    "world_offset": {"x": min_x, "y": min_y, "z": 0.0},
                    "image_size_px": {"w": int(img.shape[1]), "h": int(img.shape[0])},
                },
            }
            return geometry_json, None
        except Exception as e:  # pragma: no cover - 保護性措施
            logger.exception("AI parsing failed")
            return None, str(e)

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
            "/api/v1/3d_model/<mesh_id>",
            "/api/v1/3d_model/latest?home_id=<home_id>",
            "/api/v1/auto_generate_from_image",
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


@app.route('/api/v1/homes/<home_id>/floors', methods=['POST'])
def add_floor(home_id: str):
    """上傳單層平面圖並堆疊到指定 home。"""
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    image_file = request.files['image']

    try:
        level = int(request.form.get("level", "").strip())
    except Exception:
        return jsonify({"error": "level is required and must be an integer"}), 400

    try:
        floor_height = float(request.form.get("height", 3.0))
    except Exception:
        return jsonify({"error": "height must be numeric"}), 400

    ratio_raw = request.form.get("pixel_to_meter_ratio")
    ratio_val = AI_Perception_Service._safe_float(ratio_raw) if ratio_raw else None
    ratio = ratio_val if ratio_val else 0.01

    floor_payload = parse_single_floor_image(
        image_file.stream, level=level, floor_height=floor_height, ratio=ratio
    )
    if not floor_payload or not floor_payload.get("rooms"):
        return jsonify({"error": "Failed to parse floor image"}), 422

    params = MeshGenerationParams(wall_height=floor_height)

    room_models = []
    for room in floor_payload["rooms"]:
        room = dict(room)
        room.setdefault("openings", [])
        room.setdefault("walls", [])
        room["z_offset"] = float(floor_payload.get("z_offset", 0.0) or 0.0)
        try:
            if hasattr(Room2DInput, "model_validate"):
                room_model = Room2DInput.model_validate(room)
            else:
                room_model = Room2DInput.parse_obj(room)
        except ValidationError as e:
            return jsonify({"error": "invalid parsed room", "details": e.errors()}), 422
        room_models.append(room_model)

    request_model = Generate3DRequest(
        home_id=home_id,
        rooms=room_models,
        params=params,
        metadata={
            "original_image_url": getattr(image_file, "filename", None),
            "parsing_confidence": None,
            "pixel_to_meter_ratio": ratio,
            "z_offset": floor_payload.get("z_offset"),
            "floor_id": floor_payload.get("id"),
            "level": level,
        },
    )

    result, err = twin_service.add_floor_level(request_model)
    if err:
        return jsonify({"error": err}), 400

    return jsonify({
        "message": f"Floor level {level} appended",
        "mesh_id": result["mesh_id"],
        "result": result,
    })


@app.route('/api/v1/auto_generate_from_image', methods=['POST'])
def auto_generate_from_image():
    """接收圖片並全自動生成 3D 模型。"""
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image_file = request.files['image']
    home_id = request.form.get("home_id") or "main_home_config"
    ratio_val = AI_Perception_Service._safe_float(request.form.get("pixel_to_meter_ratio"))
    ratio = ratio_val if ratio_val else 0.01
    try:
        level = int(request.form.get("level", 1))
    except Exception:
        return jsonify({"error": "level must be integer"}), 400
    try:
        floor_height = float(request.form.get("height", 3.0))
    except Exception:
        return jsonify({"error": "height must be numeric"}), 400

    parser = FloorplanToMeshParser(pixel_to_meter_ratio=ratio)
    try:
        floor_payload = parser.parse(image_file, level=level, height=floor_height)
    except Exception as e:
        logger.exception("Error parsing image with FloorplanToMeshParser")
        return jsonify({"error": f"Image parsing failed: {e}"}), 422

    if not floor_payload.get("rooms"):
        return jsonify({"error": "Image parsing produced no rooms"}), 422

    # Pydantic validate rooms
    room_models = []
    for room in floor_payload["rooms"]:
        room = dict(room)
        room.setdefault("openings", [])
        room.setdefault("walls", [])
        room.setdefault("holes", [])
        room.setdefault("level", level)
        room["z_offset"] = float(floor_payload.get("z_offset", 0.0) or 0.0)
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
        "original_image_url": getattr(image_file, "filename", None),
        "parsing_confidence": None,
        "pixel_to_meter_ratio": ratio,
        "level": level,
        "floor_id": floor_payload.get("id"),
        "z_offset": floor_payload.get("z_offset"),
        "source": "floorplan_to_mesh_parser",
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
        "message": "3D Model generated from image",
        "parsed_geometry": floor_payload,
        "mesh_id": result["mesh_id"],
        "result": result,
    })


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
        dxf_payload = parser.parse(file, level=level, height=floor_height)
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
