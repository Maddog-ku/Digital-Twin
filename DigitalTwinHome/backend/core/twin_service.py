# core/twin_service.py

import time
import random
import logging
from typing import Optional, Tuple, Any, Dict, List
from threading import Thread, Event, Lock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

# 引入 ORM 模型和數據類
from .models import (
    HomeTwin, Room, Sensor,
    Base, HomeTwinModel, RoomModel, SensorModel
)
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

    def __new__(cls):
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

        self._constructed = True

    def initialize(self):
        """初始化 ORM 連線、創建表格並載入/設定配置"""
        if self._is_initialized:
            return

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
