import os
from dotenv import load_dotenv

"""
後端共用設定與初始資料
"""

load_dotenv()

# --- 服務配置 (可由環境變數覆寫) ---
HOST = os.getenv('APP_HOST', '0.0.0.0')
PORT = int(os.getenv('APP_PORT', '5050'))
SIMULATION_INTERVAL = float(os.getenv('SIMULATION_INTERVAL', '2'))

# --- 模擬感測器狀態列舉 ---
MOTION_STATUS = ['idle', 'detected']
DOOR_STATUS = ['closed', 'open']
SMOKE_STATUS = ['normal', 'alarm']

# --- 初始住家配置 ---
INITIAL_HOME_CONFIG = {
    "home_id": "My_Smart_Home_001",
    "rooms": [
        {
            "id": "room_a",
            "name": "主臥室",
            "sensors": [
                {"id": "motion_01", "type": "PIR", "status": "idle", "location": [1.5, 0.2, 0]},
                {"id": "door_01", "type": "DoorContact", "status": "closed", "location": [3.0, 0.5, 0]}
            ]
        },
        {
            "id": "room_b",
            "name": "客廳",
            "sensors": [
                {"id": "smoke_01", "type": "Smoke", "status": "normal", "location": [0, 2.5, 0]},
                {"id": "temp_02", "type": "Temperature", "status": "24.5°C", "location": [-1.0, 0.2, 0]}
            ]
        }
    ]
}

# --- PostgreSQL 配置 (從環境變數讀取) ---
POSTGRES_USER = os.getenv('POSTGRES_USER', 'dogmad')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'dogmad')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'digital_twin_db')

# SQLAlchemy 連線字串 (用於 core/twin_service.py 連線)
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
    f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)
