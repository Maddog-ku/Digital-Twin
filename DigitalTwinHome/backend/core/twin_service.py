# core/twin_service.py

import json
import time
import random
import logging
from datetime import datetime, timezone
from math import atan2, hypot
from uuid import uuid4
from typing import Optional, Tuple, Any, Dict, List
from threading import Thread, Event, Lock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

# 引入 ORM 模型和數據類
from .models import (
    HomeTwin, Room, Sensor,
    Base, HomeTwinModel, RoomModel, SensorModel, HomeMeshModel
)

from .schemas import Generate3DRequest, MeshData, MeshPart
# 引入配置
from config import (
    INITIAL_HOME_CONFIG,
    SIMULATION_INTERVAL,
    MOTION_STATUS,
    DOOR_STATUS,
    SMOKE_STATUS,
    SQLALCHEMY_DATABASE_URI
)

# ----------------------------------------------------------------------
# 服務層核心：DigitalTwinService
# ----------------------------------------------------------------------

class DigitalTwinService:
    """管理數位孿生狀態和數據模擬的單例服務，整合 PostgreSQL 持久化"""
    
    _instance: Optional['DigitalTwinService'] = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        """實作單例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._is_initialized = False
        return cls._instance

    def __init__(self, logger: Optional[logging.Logger] = None):
        """初始化服務所需的共享資源"""
        # 避免重複初始化單例實例
        if getattr(self, "_constructed", False):
            if logger:
                self.logger = logger
            return

        self.logger = logger or logging.getLogger('digital_twin_service')
        self.thread: Optional[Thread] = None
        self.thread_stop_event = Event()
        self.socket_io_hook = None
        self.data_lock = Lock()
        self.Session = None  # SQLAlchemy Session 工廠
        self.mesh_store: Dict[str, Dict[str, Any]] = {}

        self._constructed = True

    def _pydantic_dump(self, model: Any) -> Any:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        if hasattr(model, "dict"):
            return model.dict()
        return model

    def initialize(self):
        """初始化 ORM 連線、創建表格並載入/設定配置"""
        if self._is_initialized:
            return

        # 確保 logger 已設定（即便 __init__ 省略或 logger=None）
        if not getattr(self, "logger", None):
            self.logger = logging.getLogger('digital_twin_service')

        self.logger.info("Connecting to PostgreSQL...")
        try:
            # 建立資料庫引擎
            self.engine = create_engine(SQLALCHEMY_DATABASE_URI) 
            # 創建會話工廠
            self.Session = sessionmaker(bind=self.engine)
            
            # 自動創建表格 (如果不存在)
            Base.metadata.create_all(self.engine)
            self.logger.info("PostgreSQL tables checked/created.")
            
        except Exception as e:
            self.logger.error(f"Error connecting to PostgreSQL or creating tables: {e}")
            # 嚴重錯誤，無法使用 DB，但仍需載入配置到記憶體
            self.Session = None
        
        # 載入配置 (從 DB 或 INITIAL_HOME_CONFIG)
        self.home_twin = self._load_initial_config(INITIAL_HOME_CONFIG)
        
        self._is_initialized = True
        
    # --- 數據持久化與載入 ---

    def _load_initial_config(self, default_config: dict) -> HomeTwin:
        """從 DB 載入配置，如果不存在則使用預設配置並寫入 DB"""
        if not self.Session:
            self.logger.warning("DB connection failed. Running in memory-only mode.")
            return self._load_from_dict(default_config)

        session: Session = self.Session()
        try:
            # 1. 檢查 DB 是否有配置
            rooms_db = session.query(RoomModel).all()
            home_config_db = session.get(HomeTwinModel, 'main_home_config')
            
            if not rooms_db:
                # 2. 資料庫無配置：寫入預設配置
                self.logger.info("Configuration not found in DB. Writing default config.")
                self._write_initial_config_to_db(session, default_config)
                # 重新查詢載入
                rooms_db = session.query(RoomModel).all()
                home_config_db = session.get(HomeTwinModel, 'main_home_config')
            else:
                self.logger.info("Configuration loaded from PostgreSQL (Persistent).")

            # 3. 從 DB ORM 模型轉換為 Python 數據類 (In-Memory Model)
            return self._load_from_db_models(home_config_db, rooms_db)
            
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.error(f"PostgreSQL Load Error: {e}. Falling back to default config.")
            return self._load_from_dict(default_config)
        finally:
            session.close()

    def _write_initial_config_to_db(self, session: Session, default_config: dict):
        """將預設配置寫入空的資料庫"""
        for r_config in default_config.get("rooms", []):
            room_db = RoomModel(id=r_config['id'], name=r_config['name'])
            for s_config in r_config.get("sensors", []):
                sensor_db = SensorModel(
                    id=s_config['id'],
                    type=s_config['type'],
                    location_x=s_config['location'][0],
                    location_y=s_config['location'][1],
                    location_z=s_config['location'][2],
                    status=s_config.get('status', 'unknown'),
                    is_alert=self._is_alert(s_config['type'], s_config.get('status', 'unknown'))
                )
                room_db.sensors.append(sensor_db)
            session.add(room_db)
        
        home_config_db = HomeTwinModel(home_id='main_home_config', security_status='Safe')
        session.add(home_config_db)
        session.commit()
        self.logger.info("Default configuration successfully written to DB.")

    def _load_from_db_models(self, home_db: HomeTwinModel, rooms_db: List[RoomModel]) -> HomeTwin:
        """從 ORM 模型轉換為 In-Memory 數據類"""
        rooms = {}
        for room_db in rooms_db:
            sensors = {}
            for sensor_db in room_db.sensors:
                sensor = Sensor(
                    id=sensor_db.id,
                    type=sensor_db.type,
                    location=[sensor_db.location_x, sensor_db.location_y, sensor_db.location_z],
                    status=sensor_db.status,
                    is_alert=sensor_db.is_alert
                )
                sensors[sensor.id] = sensor
            rooms[room_db.id] = Room(id=room_db.id, name=room_db.name, sensors=sensors)
            
        return HomeTwin(
            home_id=home_db.home_id, 
            rooms=rooms,
            security_status=home_db.security_status
        )

    def _load_from_dict(self, config: dict) -> HomeTwin:
        """從 config.py 字典建立 HomeTwin 物件 (回退/記憶體模式)"""
        # ... (此方法保持不變，用於回退)
        rooms = {}
        for r_config in config.get("rooms", []):
            sensors = {}
            for s_config in r_config.get("sensors", []):
                status = s_config.get('status', 'unknown')
                sensor = Sensor(
                    id=s_config['id'],
                    type=s_config['type'],
                    location=s_config.get('location'),
                    status=status,
                    is_alert=self._is_alert(s_config.get('type'), status)
                )
                sensors[sensor.id] = sensor
            room = Room(id=r_config['id'], name=r_config['name'], sensors=sensors)
            rooms[room.id] = room
        return HomeTwin(home_id=config['home_id'], rooms=rooms)

    def _is_alert(self, sensor_type: str, status: Any) -> bool:
        """根據感測器型態與狀態判斷是否警報"""
        if sensor_type == 'PIR':
            return status == 'detected'
        if sensor_type == 'DoorContact':
            return status == 'open'
        if sensor_type == 'Smoke':
            return status == 'alarm'
        if sensor_type == 'Temperature':
            try:
                # 提取數值並判斷是否超過閾值 (35.0°C)
                value = float(str(status).replace('°C', ''))
            except (ValueError, TypeError):
                return False
            return value > 35.0
        return False

    def _generate_new_status(self, sensor: Sensor) -> Tuple[Any, bool]:
        """為模擬器生成新的感測器狀態並判斷是否警報"""
        sensor_type = sensor.type
        if sensor_type == 'PIR':
            new_status = random.choice(MOTION_STATUS)
        elif sensor_type == 'DoorContact':
            new_status = random.choice(DOOR_STATUS)
        elif sensor_type == 'Smoke':
            new_status = random.choice(SMOKE_STATUS)
        elif sensor_type == 'Temperature':
            try:
                base_temp = float(str(sensor.status).replace('°C', ''))
            except (ValueError, TypeError):
                base_temp = 24.0
            new_temp = base_temp + random.uniform(-1.0, 1.5)
            new_status = f"{new_temp:.1f}°C"
        else:
            new_status = sensor.status

        return new_status, self._is_alert(sensor_type, new_status)


    # --- 綜合安全狀態判斷邏輯 (已實作) ---
    def _evaluate_overall_status(self) -> str:
        """判斷並更新 HomeTwin 的綜合安全狀態"""
        with self.data_lock:
            is_alert_active = False
            is_critical = False

            for room in self.home_twin.rooms.values():
                for sensor in room.sensors.values():
                    if sensor.is_alert:
                        is_alert_active = True
                        if sensor.type == 'Smoke':
                            is_critical = True
                            break
                if is_critical:
                    break

            old_status = self.home_twin.security_status
            if is_critical:
                new_status = "CRITICAL"
            elif is_alert_active:
                new_status = "WARNING"
            else:
                new_status = "Safe"

            status_changed = old_status != new_status
            if status_changed:
                # 更新 In-Memory Model 
                self.home_twin.security_status = new_status

        if status_changed:
            # 立即推送給前端
            if self.socket_io_hook:
                self.socket_io_hook.emit('security_status_update', {'status': new_status}, namespace='/twin')
            self.logger.warning(f"Overall Security Status changed: {old_status} -> {new_status}")
        
        return new_status

    # --- 持久化與廣播核心方法 (替換舊的純記憶體方法) ---
    def _persist_and_broadcast_update(self, room_id: str, sensor_to_update: Sensor, update_payload: dict):
        """將狀態持久化到 DB 並透過 SocketIO 推送"""
        
        # 1. 執行綜合狀態判斷 (更新 self.home_twin.security_status)
        overall_status = self._evaluate_overall_status()

        # 2. 透過 SocketIO hook 推送 (數據與綜合狀態)
        if self.socket_io_hook:
            self.socket_io_hook.emit('sensor_update', update_payload, namespace='/twin')

        # 3. 持久化到 DB
        if self.Session:
            session: Session = self.Session()
            try:
                # 使用更新語句，效率高於先查再存
                session.query(SensorModel).filter_by(id=sensor_to_update.id).update({
                    SensorModel.status: str(sensor_to_update.status),
                    SensorModel.is_alert: sensor_to_update.is_alert
                })
                # 更新 HomeTwin 總體狀態
                session.query(HomeTwinModel).filter_by(home_id='main_home_config').update({
                    HomeTwinModel.security_status: overall_status
                })
                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                self.logger.error(f"PostgreSQL Persistence Error: {e}")
            finally:
                session.close()

    # --- 數據獲取 ---
    def get_full_config(self) -> dict:
        """返回完整的數位孿生數據 (供 REST API 使用)"""
        with self.data_lock:
            return self.home_twin.to_dict()

    def get_room_sensors(self, room_id: str) -> List[Sensor]:
        """獲取特定房間的感測器列表"""
        with self.data_lock:
            room = self.home_twin.rooms.get(room_id)
            if room:
                return list(room.sensors.values())
            return []

    # --- 2D -> 3D Mesh 生成與持久化 ---

    def generate_3d_model(
        self, request_model: Generate3DRequest
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """接收已驗證的 2D 平面圖資料，生成並持久化 3D mesh，回傳 mesh_id 與查詢資訊。"""
        try:
            mesh = self._generate_3d_mesh(request_model)
        except Exception as e:
            self.logger.exception("3D mesh generation failed")
            return None, str(e)

        mesh_id = str(uuid4())
        mesh_dict = self._pydantic_dump(mesh)
        request_dict = self._pydantic_dump(request_model)
        params_dict = self._pydantic_dump(request_model.params)
        image_meta = request_model.metadata or {}
        original_image_url = image_meta.get("original_image_url") or image_meta.get("image_url")
        parsing_confidence = image_meta.get("parsing_confidence")

        persisted = False
        if self.Session:
            session: Session = self.Session()
            try:
                mesh_db = HomeMeshModel(
                    id=mesh_id,
                    home_id=request_model.home_id,
                    mesh_format="mesh_json_v2",
                    mesh_data=mesh_dict,
                    source_2d=request_dict,
                    params=params_dict,
                    original_image_url=original_image_url,
                    parsing_confidence=parsing_confidence,
                )
                session.add(mesh_db)
                session.commit()
                persisted = True
            except SQLAlchemyError as e:
                session.rollback()
                self.logger.error(
                    f"PostgreSQL Persistence Error (mesh): {e}. Falling back to memory store."
                )
            finally:
                session.close()

        if not persisted:
            created_at_ts = time.time()
            created_at = datetime.now(timezone.utc).isoformat()
            with self.data_lock:
                self.mesh_store[mesh_id] = {
                    "id": mesh_id,
                    "home_id": request_model.home_id,
                    "mesh_format": "mesh_json_v2",
                    "mesh_data": mesh_dict,
                    "source_2d": request_dict,
                    "params": params_dict,
                    "created_at": created_at,
                    "created_at_ts": created_at_ts,
                    "original_image_url": original_image_url,
                    "parsing_confidence": parsing_confidence,
                }

        response = {
            "mesh_id": mesh_id,
            "home_id": request_model.home_id,
            "mesh_format": "mesh_json_v2",
            "world_offset": (mesh_dict.get("metadata") or {}).get("world_offset"),
            "original_image_url": original_image_url,
            "parsing_confidence": parsing_confidence,
            "parts": {
                "floor": {
                    "vertex_count": len(mesh.floor.vertices),
                    "face_count": len(mesh.floor.faces),
                },
                "walls": {
                    "vertex_count": len(mesh.walls.vertices),
                    "face_count": len(mesh.walls.faces),
                },
                "ceiling": {
                    "vertex_count": len(mesh.ceiling.vertices),
                    "face_count": len(mesh.ceiling.faces),
                },
            },
            "model_endpoint": f"/api/v1/3d_model/{mesh_id}",
            "persisted": persisted,
        }
        return response, None

    def add_floor_level(
        self,
        request_model: Generate3DRequest,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """生成單層 mesh，並將結果堆疊到最新的 home mesh list 內。"""
        try:
            mesh = self._generate_3d_mesh(request_model)
        except Exception as e:
            self.logger.exception("Floor mesh generation failed")
            return None, str(e)

        room_meta = request_model.rooms[0] if request_model.rooms else None
        level = getattr(room_meta, "level", None)
        z_offset = float(getattr(room_meta, "z_offset", 0.0) or (request_model.metadata or {}).get("z_offset", 0.0) or 0.0)
        floor_height = float(
            getattr(room_meta, "height", request_model.params.wall_height)
        )

        new_entry = {
            "level": level,
            "z_offset": z_offset,
            "height": floor_height,
            "mesh": self._pydantic_dump(mesh),
            "metadata": {
                "params": self._pydantic_dump(request_model.params),
                "rooms": getattr(mesh, "metadata", {}).get("rooms") if hasattr(mesh, "metadata") else {},
                "source": request_model.metadata or {},
            },
        }

        existing_stack: List[Dict[str, Any]] = []
        existing_meta: Dict[str, Any] = {}
        latest, _ = self.get_latest_3d_model_for_home(request_model.home_id)
        if latest and isinstance(latest.get("data"), list):
            existing_stack = latest["data"]
            existing_meta = latest.get("metadata") or {}

        merged_stack = list(existing_stack)
        merged_stack.append(new_entry)

        mesh_id = str(uuid4())
        original_image_url = (request_model.metadata or {}).get("original_image_url")
        parsing_confidence = (request_model.metadata or {}).get("parsing_confidence")

        persisted = False
        if self.Session:
            session: Session = self.Session()
            try:
                mesh_db = HomeMeshModel(
                    id=mesh_id,
                    home_id=request_model.home_id,
                    mesh_format="stacked_mesh_v1",
                    mesh_data=merged_stack,
                    source_2d=[self._pydantic_dump(r) for r in request_model.rooms],
                    params=self._pydantic_dump(request_model.params),
                    original_image_url=original_image_url,
                    parsing_confidence=parsing_confidence,
                )
                session.add(mesh_db)
                session.commit()
                persisted = True
            except SQLAlchemyError as e:
                session.rollback()
                self.logger.error(
                    f"PostgreSQL Persistence Error (floor stack): {e}. Falling back to memory store."
                )
            finally:
                session.close()

        if not persisted:
            created_at_ts = time.time()
            created_at = datetime.now(timezone.utc).isoformat()
            with self.data_lock:
                self.mesh_store[mesh_id] = {
                    "id": mesh_id,
                    "home_id": request_model.home_id,
                    "mesh_format": "stacked_mesh_v1",
                    "mesh_data": merged_stack,
                    "source_2d": [self._pydantic_dump(r) for r in request_model.rooms],
                    "params": self._pydantic_dump(request_model.params),
                    "created_at": created_at,
                    "created_at_ts": created_at_ts,
                    "original_image_url": original_image_url,
                    "parsing_confidence": parsing_confidence,
                }

        response = {
            "mesh_id": mesh_id,
            "home_id": request_model.home_id,
            "mesh_format": "stacked_mesh_v1",
            "floors_count": len(merged_stack),
            "levels": [entry.get("level") for entry in merged_stack],
            "original_image_url": original_image_url,
            "parsing_confidence": parsing_confidence,
            "model_endpoint": f"/api/v1/3d_model/{mesh_id}",
            "persisted": persisted,
        }
        return response, None

    def get_3d_model(self, mesh_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """讀取指定 mesh_id 的 3D mesh (JSON vertices/faces)。"""
        if self.Session:
            session: Session = self.Session()
            try:
                mesh_db = session.get(HomeMeshModel, mesh_id)
                if not mesh_db:
                    return None, f"mesh_id '{mesh_id}' not found"

                mesh_payload = mesh_db.mesh_data
                if isinstance(mesh_payload, str):
                    mesh_payload = json.loads(mesh_payload)

                return (
                    {
                        "mesh_id": mesh_db.id,
                        "home_id": mesh_db.home_id,
                        "mesh_format": mesh_db.mesh_format,
                        "data": mesh_payload,
                        "created_at": mesh_db.created_at.isoformat() if mesh_db.created_at else None,
                        "original_image_url": mesh_db.original_image_url,
                        "parsing_confidence": mesh_db.parsing_confidence,
                        "metadata": getattr(mesh_payload, "metadata", None) if isinstance(mesh_payload, dict) else None,
                    },
                    None,
                )
            except SQLAlchemyError as e:
                self.logger.error(f"PostgreSQL Load Error (mesh): {e}")
            finally:
                session.close()

        with self.data_lock:
            mesh = self.mesh_store.get(mesh_id)
            if not mesh:
                return None, f"mesh_id '{mesh_id}' not found"
            return (
                {
                    "mesh_id": mesh["id"],
                    "home_id": mesh["home_id"],
                    "mesh_format": mesh["mesh_format"],
                    "data": mesh["mesh_data"],
                    "created_at": mesh.get("created_at"),
                    "original_image_url": mesh.get("original_image_url"),
                    "parsing_confidence": mesh.get("parsing_confidence"),
                },
                None,
            )

    def get_latest_3d_model_for_home(
        self, home_id: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """取得某個 home_id 最新生成的 mesh。"""
        if self.Session:
            session: Session = self.Session()
            try:
                mesh_db = (
                    session.query(HomeMeshModel)
                    .filter_by(home_id=home_id)
                    .order_by(HomeMeshModel.created_at.desc())
                    .first()
                )
                if not mesh_db:
                    return None, f"home_id '{home_id}' has no meshes"

                mesh_payload = mesh_db.mesh_data
                if isinstance(mesh_payload, str):
                    mesh_payload = json.loads(mesh_payload)
                return (
                    {
                        "mesh_id": mesh_db.id,
                        "home_id": mesh_db.home_id,
                        "mesh_format": mesh_db.mesh_format,
                        "data": mesh_payload,
                        "created_at": mesh_db.created_at.isoformat() if mesh_db.created_at else None,
                        "original_image_url": mesh_db.original_image_url,
                        "parsing_confidence": mesh_db.parsing_confidence,
                        "metadata": getattr(mesh_payload, "metadata", None) if isinstance(mesh_payload, dict) else None,
                    },
                    None,
                )
            except SQLAlchemyError as e:
                self.logger.error(f"PostgreSQL Load Error (mesh): {e}")
            finally:
                session.close()

        with self.data_lock:
            meshes = [m for m in self.mesh_store.values() if m.get("home_id") == home_id]
            if not meshes:
                return None, f"home_id '{home_id}' has no meshes"
            latest = max(meshes, key=lambda m: m.get("created_at_ts", 0))
            return (
                {
                    "mesh_id": latest["id"],
                    "home_id": latest["home_id"],
                    "mesh_format": latest["mesh_format"],
                    "data": latest["mesh_data"],
                    "created_at": latest.get("created_at"),
                    "original_image_url": latest.get("original_image_url"),
                    "parsing_confidence": latest.get("parsing_confidence"),
                    "metadata": None,
                },
                None,
            )

    def _generate_3d_mesh(self, request_model: Generate3DRequest) -> MeshData:
        """將 2D 平面圖輪廓轉換為可渲染的 3D Mesh。

        v2 實作重點：
        - Mesh 分離：floor / walls / ceiling（方便前端分別上材質）
        - doors/windows：在 walls 上做矩形孔洞裁切（無需額外依賴即可工作）
        - world_offset：將幾何中心平移到世界原點附近，並回傳 offset 供感測器座標對齊
        - 以 Z 軸為 Up 軸（前端如採 Y-Up，需做軸轉換）
        """

        world_offset = self._calculate_world_offset(request_model.rooms)
        x_offset = float(world_offset["x"])
        y_offset = float(world_offset["y"])
        z_offset = float(world_offset.get("z", 0.0))

        floor_vertices: List[Tuple[float, float, float]] = []
        floor_faces: List[Tuple[int, int, int]] = []
        ceiling_vertices: List[Tuple[float, float, float]] = []
        ceiling_faces: List[Tuple[int, int, int]] = []
        walls_vertices: List[Tuple[float, float, float]] = []
        walls_faces: List[Tuple[int, int, int]] = []

        rooms_meta: Dict[str, Any] = {}
        default_height = request_model.params.wall_height

        use_csg = bool(getattr(request_model.params, "use_csg", False))
        csg_summary: Dict[str, Any] = {"requested": use_csg, "used": False, "reason": None}

        for room in request_model.rooms:
            if room.holes:
                raise ValueError(
                    f"Room '{room.id}' contains holes; this mesh generator does not support holes yet."
                )

            ring_2d = self._clean_ring(list(room.polygon))
            if len(ring_2d) < 3:
                raise ValueError(f"Room '{room.id}' polygon must have at least 3 non-collinear points.")

            if self._signed_area_2d(ring_2d) < 0:
                ring_2d.reverse()

            room_height = float(room.height or default_height)
            triangles_2d = self._triangulate_ear_clipping(ring_2d)
            if not triangles_2d:
                raise ValueError(
                    f"Room '{room.id}' polygon triangulation failed (non-simple polygon or unsupported geometry)."
                )

            room_z_offset = float(getattr(room, "z_offset", 0.0) or 0.0)
            base_z = room_z_offset - z_offset

            # Floor (Z = base_z) - face upward (+Z)
            floor_vertex_offset = len(floor_vertices)
            floor_vertices.extend([(x - x_offset, y - y_offset, base_z) for x, y in ring_2d])
            floor_faces.extend(
                [(a + floor_vertex_offset, b + floor_vertex_offset, c + floor_vertex_offset) for a, b, c in triangles_2d]
            )

            # Ceiling (Z = base_z + room_height) - face downward (-Z) so it's visible from inside
            ceiling_vertex_offset = len(ceiling_vertices)
            ceiling_vertices.extend(
                [(x - x_offset, y - y_offset, base_z + room_height) for x, y in ring_2d]
            )
            ceiling_faces.extend(
                [
                    (a + ceiling_vertex_offset, c + ceiling_vertex_offset, b + ceiling_vertex_offset)
                    for a, b, c in triangles_2d
                ]
            )

            # Walls - v2 supports door/window cutouts
            room_walls_part: Optional[Dict[str, Any]] = None
            room_csg_info: Optional[Dict[str, Any]] = None
            if use_csg:
                room_walls_part, room_csg_info = self._try_generate_walls_mesh_csg(
                    ring_2d=ring_2d,
                    wall_height=room_height,
                    wall_thickness=float(request_model.params.wall_thickness),
                    openings=list(room.openings),
                    x_offset=x_offset,
                    y_offset=y_offset,
                    z_offset=base_z,
                )
                if room_walls_part is not None:
                    csg_summary["used"] = True
                elif room_csg_info and not csg_summary.get("reason"):
                    csg_summary["reason"] = room_csg_info.get("reason")

            if room_walls_part is None:
                room_walls_part = self._generate_walls_mesh_manual(
                    ring_2d=ring_2d,
                    wall_height=room_height,
                    openings=list(room.openings),
                    x_offset=x_offset,
                    y_offset=y_offset,
                    z_offset=base_z,
                    walls_override=list(room.walls),
                )

            walls_vertex_offset = len(walls_vertices)
            walls_vertices.extend(room_walls_part["vertices"])
            walls_faces.extend(
                [
                    (a + walls_vertex_offset, b + walls_vertex_offset, c + walls_vertex_offset)
                    for a, b, c in room_walls_part["faces"]
                ]
            )

            rooms_meta[room.id] = {
                "name": room.name,
                "height": room_height,
                "polygon": ring_2d,
            }

        metadata = dict(request_model.metadata or {})
        metadata.update(
            {
                "world_offset": world_offset,
                "params": self._pydantic_dump(request_model.params),
                "rooms": rooms_meta,
            }
        )
        if use_csg:
            metadata["csg"] = csg_summary

        return MeshData(
            floor=MeshPart(vertices=floor_vertices, faces=floor_faces),
            walls=MeshPart(vertices=walls_vertices, faces=walls_faces),
            ceiling=MeshPart(vertices=ceiling_vertices, faces=ceiling_faces),
            metadata=metadata,
        )

    def _calculate_world_offset(self, rooms: List[Any]) -> Dict[str, float]:
        """計算世界座標 offset (使用所有 rooms polygon/holes 的 AABB 中心)。"""
        points: List[Tuple[float, float]] = []
        for room in rooms:
            if getattr(room, "polygon", None):
                points.extend(list(room.polygon))
            for hole in getattr(room, "holes", []) or []:
                points.extend(list(hole))

        if not points:
            return {"x": 0.0, "y": 0.0, "z": 0.0}

        min_x = min(p[0] for p in points)
        max_x = max(p[0] for p in points)
        min_y = min(p[1] for p in points)
        max_y = max(p[1] for p in points)

        return {
            "x": float((min_x + max_x) / 2.0),
            "y": float((min_y + max_y) / 2.0),
            "z": 0.0,
        }

    def _generate_walls_mesh_manual(
        self,
        ring_2d: List[Tuple[float, float]],
        wall_height: float,
        openings: List[Any],
        x_offset: float,
        y_offset: float,
        z_offset: float,
        walls_override: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """建立 walls mesh（垂直面），並在牆面上裁切 door/window 的矩形孔洞。

        注意：此實作輸出的是牆面「薄殼」(zero thickness)。如需牆厚與孔洞內壁，可啟用 CSG 路徑。
        """

        segments = self._build_wall_segments(ring_2d=ring_2d, walls_override=walls_override)
        openings_by_segment = self._assign_openings_to_wall_segments(
            segments=segments, openings=openings
        )

        vertices: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, int, int]] = []

        for segment_index, segment in enumerate(segments):
            (x0, y0) = segment["start"]
            (x1, y1) = segment["end"]
            length = hypot(x1 - x0, y1 - y0)
            if length <= 1e-9:
                continue

            dir_x = (x1 - x0) / length
            dir_y = (y1 - y0) / length

            cut_rects: List[Tuple[float, float, float, float]] = []
            for opening in openings_by_segment.get(segment_index, []):
                opening_rect = self._opening_to_wall_rect(
                    opening=opening,
                    start=(x0, y0),
                    end=(x1, y1),
                    wall_length=length,
                    wall_height=wall_height,
                )
                if opening_rect is not None:
                    cut_rects.append(opening_rect)

            # Base wall rectangle in local (u,z): [0, length] x [0, wall_height]
            remaining = self._subtract_rectangles(
                base_rect=(0.0, length, 0.0, wall_height),
                subtract_rects=cut_rects,
            )
            if not remaining:
                continue

            def to_world(u: float, z: float) -> Tuple[float, float, float]:
                return (
                    (x0 + dir_x * u) - x_offset,
                    (y0 + dir_y * u) - y_offset,
                    z - z_offset,
                )

            for u_min, u_max, z_min, z_max in remaining:
                if (u_max - u_min) <= 1e-9 or (z_max - z_min) <= 1e-9:
                    continue

                v0 = to_world(u_min, z_min)
                v1 = to_world(u_max, z_min)
                v2 = to_world(u_max, z_max)
                v3 = to_world(u_min, z_max)

                v_offset = len(vertices)
                vertices.extend([v0, v1, v2, v3])

                # Face inward (towards polygon interior) for CCW polygon: reverse winding from outward.
                faces.append((v_offset + 0, v_offset + 2, v_offset + 1))
                faces.append((v_offset + 0, v_offset + 3, v_offset + 2))

        return {"vertices": vertices, "faces": faces}

    def _build_wall_segments(
        self, ring_2d: List[Tuple[float, float]], walls_override: Optional[List[Any]]
    ) -> List[Dict[str, Any]]:
        if walls_override:
            segments: List[Dict[str, Any]] = []
            for w in walls_override:
                start = tuple(w.start)
                end = tuple(w.end)
                segments.append({"id": getattr(w, "id", None), "start": start, "end": end})
            return segments

        segments = []
        n = len(ring_2d)
        for i in range(n):
            segments.append({"id": f"edge_{i}", "start": ring_2d[i], "end": ring_2d[(i + 1) % n]})
        return segments

    def _assign_openings_to_wall_segments(
        self, segments: List[Dict[str, Any]], openings: List[Any]
    ) -> Dict[int, List[Any]]:
        assigned: Dict[int, List[Any]] = {}
        if not segments or not openings:
            return assigned

        id_to_index = {
            s["id"]: idx for idx, s in enumerate(segments) if s.get("id") is not None
        }

        for opening in openings:
            wall_id = getattr(opening, "wall_id", None)
            if wall_id is not None and wall_id in id_to_index:
                assigned.setdefault(id_to_index[wall_id], []).append(opening)
                continue

            center = getattr(opening, "center", None)
            if not center:
                continue

            cx, cy = center
            best_idx: Optional[int] = None
            best_dist = float("inf")
            for idx, seg in enumerate(segments):
                dist = self._distance_point_to_segment_2d((cx, cy), seg["start"], seg["end"])
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

            if best_idx is not None:
                assigned.setdefault(best_idx, []).append(opening)

        return assigned

    def _opening_to_wall_rect(
        self,
        opening: Any,
        start: Tuple[float, float],
        end: Tuple[float, float],
        wall_length: float,
        wall_height: float,
    ) -> Optional[Tuple[float, float, float, float]]:
        """將 opening（含 center/width/height/bottom）轉成牆面 local (u,z) 矩形 [u0,u1]x[z0,z1]。"""
        center = getattr(opening, "center", None)
        if center:
            cx, cy = center
            t = self._project_param_on_segment_2d((cx, cy), start, end)
            u_center = t * wall_length
        else:
            # If the opening was assigned via wall_id without a center, fall back to wall midpoint.
            u_center = wall_length / 2.0

        width = float(getattr(opening, "width", 0.0) or 0.0)
        height = float(getattr(opening, "height", 0.0) or 0.0)
        bottom = float(getattr(opening, "bottom", 0.0) or 0.0)

        if width <= 0 or height <= 0:
            return None

        u0 = u_center - width / 2.0
        u1 = u_center + width / 2.0
        z0 = bottom
        z1 = bottom + height

        # Clamp to wall extents
        u0 = max(0.0, min(wall_length, u0))
        u1 = max(0.0, min(wall_length, u1))
        z0 = max(0.0, min(wall_height, z0))
        z1 = max(0.0, min(wall_height, z1))

        if u1 - u0 <= 1e-9 or z1 - z0 <= 1e-9:
            return None

        return (u0, u1, z0, z1)

    def _subtract_rectangles(
        self,
        base_rect: Tuple[float, float, float, float],
        subtract_rects: List[Tuple[float, float, float, float]],
    ) -> List[Tuple[float, float, float, float]]:
        """從 base_rect 減去多個 axis-aligned 矩形，回傳剩餘的矩形集合（互不重疊）。"""
        remaining = [base_rect]

        def intersect(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]):
            ax0, ax1, ay0, ay1 = a
            bx0, bx1, by0, by1 = b
            ix0 = max(ax0, bx0)
            ix1 = min(ax1, bx1)
            iy0 = max(ay0, by0)
            iy1 = min(ay1, by1)
            if ix1 - ix0 <= 1e-9 or iy1 - iy0 <= 1e-9:
                return None
            return ix0, ix1, iy0, iy1

        for sub in subtract_rects:
            next_remaining: List[Tuple[float, float, float, float]] = []
            for rect in remaining:
                inter = intersect(rect, sub)
                if inter is None:
                    next_remaining.append(rect)
                    continue

                x0, x1, y0, y1 = rect
                ix0, ix1, iy0, iy1 = inter

                # Left / Right
                if ix0 > x0 + 1e-9:
                    next_remaining.append((x0, ix0, y0, y1))
                if ix1 < x1 - 1e-9:
                    next_remaining.append((ix1, x1, y0, y1))

                # Bottom / Top (within intersection band)
                if iy0 > y0 + 1e-9:
                    next_remaining.append((ix0, ix1, y0, iy0))
                if iy1 < y1 - 1e-9:
                    next_remaining.append((ix0, ix1, iy1, y1))

            remaining = next_remaining
            if not remaining:
                break

        return remaining

    def _distance_point_to_segment_2d(
        self,
        p: Tuple[float, float],
        a: Tuple[float, float],
        b: Tuple[float, float],
    ) -> float:
        px, py = p
        ax, ay = a
        bx, by = b
        abx = bx - ax
        aby = by - ay
        apx = px - ax
        apy = py - ay
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return hypot(px - ax, py - ay)
        t = (apx * abx + apy * aby) / denom
        t = max(0.0, min(1.0, t))
        cx = ax + t * abx
        cy = ay + t * aby
        return hypot(px - cx, py - cy)

    def _project_param_on_segment_2d(
        self,
        p: Tuple[float, float],
        a: Tuple[float, float],
        b: Tuple[float, float],
    ) -> float:
        """回傳投影參數 t（clamped to [0,1]），使得 a + t*(b-a) 為 p 在 segment 上的投影點。"""
        px, py = p
        ax, ay = a
        bx, by = b
        abx = bx - ax
        aby = by - ay
        denom = (abx * abx) + (aby * aby)
        if denom <= 1e-12:
            return 0.0
        t = ((px - ax) * abx + (py - ay) * aby) / denom
        return max(0.0, min(1.0, t))

    def _try_generate_walls_mesh_csg(
        self,
        ring_2d: List[Tuple[float, float]],
        wall_height: float,
        wall_thickness: float,
        openings: List[Any],
        x_offset: float,
        y_offset: float,
        z_offset: float,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """使用 trimesh + shapely 進行 CSG 布林裁切（牆厚 + 洞內壁）。

        若缺少依賴或布林引擎不可用，回傳 (None, reason) 並由呼叫方 fallback 到手工裁切。
        """
        try:
            import trimesh  # type: ignore
            from shapely.geometry import Polygon  # type: ignore
        except Exception as e:  # pragma: no cover
            return None, {"reason": f"CSG dependencies missing: {e}"}

        if wall_thickness <= 0:
            return None, {"reason": "wall_thickness must be > 0 for CSG"}

        try:
            room_poly = Polygon(ring_2d)
            if not room_poly.is_valid:
                room_poly = room_poly.buffer(0)

            # Build a wall footprint ring around the polygon boundary (centered thickness)
            outer = room_poly.buffer(wall_thickness / 2.0, join_style=2)
            inner = room_poly.buffer(-wall_thickness / 2.0, join_style=2)
            wall_footprint = outer.difference(inner) if not inner.is_empty else outer

            wall_mesh = trimesh.creation.extrude_polygon(wall_footprint, wall_height)
            wall_mesh.apply_translation([-x_offset, -y_offset, -z_offset])
        except Exception as e:
            return None, {"reason": f"CSG wall extrusion failed: {e}"}

        cutters = []
        for opening in openings:
            center = getattr(opening, "center", None)
            if not center:
                continue
            cx, cy = center
            width = float(getattr(opening, "width", 0.0) or 0.0)
            height = float(getattr(opening, "height", 0.0) or 0.0)
            bottom = float(getattr(opening, "bottom", 0.0) or 0.0)
            if width <= 0 or height <= 0:
                continue

            # Find nearest edge direction for cutter orientation
            nearest_dir = self._nearest_edge_direction(ring_2d=ring_2d, point=(cx, cy))
            angle = atan2(nearest_dir[1], nearest_dir[0])

            box = trimesh.creation.box(extents=[width, wall_thickness * 2.2, height])
            # rotate around Z then translate to opening center
            rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
            box.apply_transform(rot)
            box.apply_translation([cx - x_offset, cy - y_offset, (bottom + height / 2.0) - z_offset])
            cutters.append(box)

        if cutters:
            try:
                # boolean.difference: first is base, rest are subtractors
                wall_mesh = trimesh.boolean.difference([wall_mesh] + cutters)
            except Exception as e:
                return None, {"reason": f"CSG boolean difference failed: {e}"}

        if wall_mesh is None:
            return None, {"reason": "CSG boolean produced empty mesh"}

        try:
            # Keep vertical faces only (walls). abs(n.z) near 0 => vertical
            normals = wall_mesh.face_normals
            vertical = [i for i, n in enumerate(normals) if abs(float(n[2])) < 0.2]
            if not vertical:
                return None, {"reason": "CSG produced no vertical faces"}
            wall_shell = wall_mesh.submesh([vertical], append=True, repair=False)

            vertices = [tuple(map(float, v)) for v in wall_shell.vertices.tolist()]
            faces = [tuple(map(int, f)) for f in wall_shell.faces.tolist()]
            return {"vertices": vertices, "faces": faces}, {"reason": None}
        except Exception as e:
            return None, {"reason": f"CSG post-process failed: {e}"}

    def _nearest_edge_direction(
        self, ring_2d: List[Tuple[float, float]], point: Tuple[float, float]
    ) -> Tuple[float, float]:
        """回傳 point 最近的 polygon 邊方向向量（單位化）。"""
        px, py = point
        best = (1.0, 0.0)
        best_dist = float("inf")
        n = len(ring_2d)
        for i in range(n):
            a = ring_2d[i]
            b = ring_2d[(i + 1) % n]
            dist = self._distance_point_to_segment_2d((px, py), a, b)
            if dist < best_dist:
                best_dist = dist
                dx = b[0] - a[0]
                dy = b[1] - a[1]
                length = hypot(dx, dy)
                if length > 1e-12:
                    best = (dx / length, dy / length)
        return best

    def _signed_area_2d(self, ring: List[Tuple[float, float]]) -> float:
        area = 0.0
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            area += (x1 * y2) - (x2 * y1)
        return area / 2.0

    def _clean_ring(self, ring: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(ring) < 3:
            return ring

        cleaned: List[Tuple[float, float]] = []
        for point in ring:
            if not cleaned or point != cleaned[-1]:
                cleaned.append(point)
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
            cleaned.pop()

        def is_collinear(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> bool:
            ax, ay = a
            bx, by = b
            cx, cy = c
            cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
            return abs(cross) < 1e-9

        i = 0
        while len(cleaned) >= 3 and i < len(cleaned):
            prev = cleaned[i - 1]
            curr = cleaned[i]
            nxt = cleaned[(i + 1) % len(cleaned)]
            if is_collinear(prev, curr, nxt):
                cleaned.pop(i)
                i = max(i - 1, 0)
                continue
            i += 1

        return cleaned

    def _extrude_polygon_to_prism(
        self, ring_2d: List[Tuple[float, float]], height: float, floor_z: float = 0.0
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
        triangles_2d = self._triangulate_ear_clipping(ring_2d)
        if not triangles_2d:
            raise ValueError("Polygon triangulation failed (non-simple polygon or unsupported geometry).")

        vertices: List[Tuple[float, float, float]] = []
        for x, y in ring_2d:
            vertices.append((x, y, floor_z))
        for x, y in ring_2d:
            vertices.append((x, y, floor_z + height))

        n = len(ring_2d)
        faces: List[Tuple[int, int, int]] = []

        # Bottom face (outward normal: -Z) -> reverse winding
        for a, b, c in triangles_2d:
            faces.append((a, c, b))

        # Top face (outward normal: +Z)
        for a, b, c in triangles_2d:
            faces.append((a + n, b + n, c + n))

        # Side walls
        for i in range(n):
            j = (i + 1) % n
            bottom_i = i
            bottom_j = j
            top_i = i + n
            top_j = j + n

            faces.append((bottom_i, bottom_j, top_j))
            faces.append((bottom_i, top_j, top_i))

        return vertices, faces

    def _triangulate_ear_clipping(
        self, ring: List[Tuple[float, float]]
    ) -> List[Tuple[int, int, int]]:
        """Ear clipping triangulation for a simple CCW polygon without holes."""
        n = len(ring)
        if n < 3:
            return []

        def cross(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
            ox, oy = o
            ax, ay = a
            bx, by = b
            return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

        def is_point_in_triangle(
            p: Tuple[float, float],
            a: Tuple[float, float],
            b: Tuple[float, float],
            c: Tuple[float, float],
        ) -> bool:
            # Barycentric technique with orientation tests (CCW triangle)
            c1 = cross(a, b, p)
            c2 = cross(b, c, p)
            c3 = cross(c, a, p)
            eps = 1e-12
            return c1 >= -eps and c2 >= -eps and c3 >= -eps

        indices = list(range(n))
        triangles: List[Tuple[int, int, int]] = []

        guard = 0
        while len(indices) > 3 and guard < n * n:
            guard += 1
            ear_found = False

            for idx_pos in range(len(indices)):
                prev_idx = indices[idx_pos - 1]
                curr_idx = indices[idx_pos]
                next_idx = indices[(idx_pos + 1) % len(indices)]

                prev_pt = ring[prev_idx]
                curr_pt = ring[curr_idx]
                next_pt = ring[next_idx]

                # Must be convex for CCW polygon
                if cross(prev_pt, curr_pt, next_pt) <= 1e-12:
                    continue

                # No other vertex inside the ear triangle
                is_ear = True
                for test_idx in indices:
                    if test_idx in (prev_idx, curr_idx, next_idx):
                        continue
                    if is_point_in_triangle(ring[test_idx], prev_pt, curr_pt, next_pt):
                        is_ear = False
                        break

                if not is_ear:
                    continue

                triangles.append((prev_idx, curr_idx, next_idx))
                indices.pop(idx_pos)
                ear_found = True
                break

            if not ear_found:
                break

        if len(indices) == 3:
            triangles.append((indices[0], indices[1], indices[2]))

        return triangles
            
    # --- 外部事件與模擬核心方法 (需要調整以呼叫新的持久化方法) ---

    def apply_sensor_event(
        self,
        room_id: str,
        sensor_id: str,
        sensor_type: str,
        new_status: Any,
        location: Optional[List[float]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """接受外部事件並更新模型狀態，回傳 payload 或錯誤訊息"""
        
        # 1. 執行 In-Memory 模型更新
        with self.data_lock:
            # ... (檢查 room 和 sensor 邏輯不變)
            room = self.home_twin.rooms.get(room_id)
            if not room:
                return None, f"room_id '{room_id}' not found"

            sensor = room.sensors.get(sensor_id)
            if sensor:
                sensor.type = sensor_type
                sensor.status = new_status
                sensor.is_alert = self._is_alert(sensor_type, new_status)
                if location is not None:
                    sensor.location = location
            else:
                # 如果感測器不存在，則新增 (這是高擴展性要求的一部分)
                sensor = Sensor(
                    id=sensor_id,
                    type=sensor_type,
                    status=new_status,
                    location=location or [],
                    is_alert=self._is_alert(sensor_type, new_status)
                )
                room.sensors[sensor_id] = sensor

            # 準備 payload (使用更新後的 In-Memory 狀態)
            update_payload = {
                "room_id": room_id,
                "room_name": room.name,
                "sensor_id": sensor_id,
                "new_status": sensor.status,
                "is_alert": sensor.is_alert,
                "type": sensor.type,
                "location": sensor.location,
            }
        
        # 2. 持久化到 DB 並透過 SocketIO 推送
        self._persist_and_broadcast_update(room_id, sensor, update_payload)

        return update_payload, None


    def _is_thread_alive(self) -> bool:
        """檢查背景模擬執行緒是否仍在運行"""
        return self.thread is not None and self.thread.is_alive()

    def start_simulation(self, socket_io_hook):
        """啟動感測器模擬背景執行緒"""
        self.socket_io_hook = socket_io_hook
        if self._is_thread_alive():
            self.logger.info("Sensor simulator already running.")
            return

        self.thread_stop_event.clear()
        self.thread = Thread(target=self.sensor_simulator_worker, daemon=True)
        self.thread.start()
        self.logger.info("Starting sensor simulator background thread...")

    def stop_simulation(self):
        """停止感測器模擬背景執行緒"""
        if not self._is_thread_alive():
            return

        self.logger.info("Stopping sensor simulator thread...")
        self.thread_stop_event.set()
        self.thread.join()
        self.thread = None

    def sensor_simulator_worker(self):
        """背景執行緒：模擬數據並推送"""
        self.logger.info("--- 數位孿生模擬器已啟動 ---")
        
        while not self.thread_stop_event.is_set():
            with self.data_lock:
                sensor_pool = [
                    (room.id, room.name, sensor)
                    for room in self.home_twin.rooms.values()
                    for sensor in room.sensors.values()
                ]

            if not sensor_pool:
                self.logger.warning("No sensors available for simulation. Sleeping...")
                time.sleep(SIMULATION_INTERVAL)
                continue

            room_id, room_name, sensor_to_update = random.choice(sensor_pool)

            new_status, is_alert = self._generate_new_status(sensor_to_update)

            with self.data_lock:
                sensor_to_update.status = new_status
                sensor_to_update.is_alert = is_alert
                
                update_payload = {
                    "room_id": room_id,
                    "room_name": room_name,
                    "sensor_id": sensor_to_update.id,
                    "new_status": new_status,
                    "is_alert": is_alert,
                    "type": sensor_to_update.type,
                    "location": sensor_to_update.location,
                }
            
            self._persist_and_broadcast_update(room_id, sensor_to_update, update_payload)
            
            time.sleep(SIMULATION_INTERVAL)
        self.thread = None
