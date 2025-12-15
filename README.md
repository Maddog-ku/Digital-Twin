# 🏡 數位孿生居家安全專案 (Digital Twin Home Security)

## 🌟 專案簡介
本專案旨在建立一個基於物聯網（IoT）的居家安全**數位孿生（Digital Twin）**系統。透過實時數據採集和虛擬模型，使用者可以在 Web 或原生行動應用程式（Swift/iOS/macOS）上監控、分析和模擬實體住家的安全狀態和設備配置。

**核心目標：** 實現虛擬與實體住家的 1:1 映射，提供即時狀態視覺化、異常事件警報和房間客製化配置功能。

## 💻 技術棧 (Technology Stack)

| 類別 | 組件 | 推薦技術 | 用途與說明 |
| :--- | :--- | :--- | :--- |
| **後端/核心** | 數據處理/API | Python (Flask/Django) / Node.js (Express) | 處理感測器數據、執行業務邏輯、提供 RESTful API。 |
| | 實時數據流 | MQTT Broker (e.g., Mosquitto) / WebSocket | 接收來自 IoT 設備的即時數據。 |
| | 資料庫 | MongoDB / InfluxDB | 儲存設備配置和歷史感測器數據。 |
| **前端 (Web)** | 應用框架 | React.js (with Hooks) | 建立主要儀表板和設定介面。 |
| | 3D 視覺化 | React Three Fiber (R3F) / Three.js | 渲染和互動式操作 3D 數位孿生模型。 |
| **前端 (Swift)** | 應用框架 | Swift / SwiftUI | 建立原生的 iOS/macOS 應用程式。 |
| | 網路/通訊 | URLSession / URLSessionWebSocketTask | 呼叫 REST API 和處理實時 WebSocket 連線。 |

## 🏠 專案架構圖
本專案採用典型的數位孿生架構，將實體感測器數據透過後端核心系統轉化為虛擬模型狀態，並透過 Web 和 Swift 應用展示。

## 💡 核心功能
*   **實時狀態視覺化：** 在 2D 平面圖或 3D 虛擬模型上，實時顯示感測器（門磁、煙霧、移動）的狀態變化，以顏色高亮顯示異常區域。
*   **房間客製化設定：** 使用者可以設定每個房間的名稱、擁有者，並配置該房間內部的感測器類型和位置。
*   **跨平台監控：** 支援 Web 瀏覽器和 Swift 撰寫的原生應用程式，提供一致的監控體驗。
*   **模擬模式 (Simulation Mode)：** 在數位孿生中模擬異常事件（例如：門被打開、瓦斯洩漏），用於測試警報邏輯和響應機制。
*   **歷史數據分析：** 查詢特定時間段內的感測器活動紀錄。

## ⚙️ 環境建置與安裝指南

### A. 後端環境 (Backend Setup)
1.  **安裝依賴：** 確保您已安裝 Python/Node.js 和 Docker (建議用於部署數據庫和 MQTT Broker)。
    ```bash
    # 範例：使用 Python
    pip install -r requirements.txt
    ```
2.  **啟動服務：**
    ```bash
    # 啟動 MongoDB 和 MQTT Broker 容器 (使用 docker-compose.yml)
    docker-compose up -d

    # 啟動後端 API 伺服器
    npm run start:server  # 或 python app.py
    ```
3.  **API 端點：** 後端 API 預設運行在 `http://localhost:5000` (或您設定的連接埠)。

### B. Web 前端部署 (React Setup)
1.  **進入目錄：**
    ```bash
    cd frontend/web
    ```
2.  **安裝依賴：**
    ```bash
    npm install
    ```
3.  **啟動開發伺服器：**
    ```bash
    npm run dev
    ```
    Web 應用程式將運行在 `http://localhost:5173` (或 Vite/Create React App 預設端口)。

### C. Swift 應用部署 (iOS/macOS)
1.  **軟體要求：**
    *   macOS Sonoma 或以上
    *   Xcode 15 或以上
2.  **開啟專案：**
    ```bash
    cd frontend/swift
    open DigitalTwinHome.xcodeproj
    ```
3.  **配置網路：** 確保 Swift 應用程式中定義的後端 API 地址與您後端服務器地址相符。
4.  **運行：** 選擇一個模擬器或您的實體裝置，點擊 Xcode 中的「運行」按鈕。

## 📂 專案結構

```
/DigitalTwinHome
├── backend/                  # 後端 API 與數據處理
│   ├── api/                  # REST API 路由定義
│   ├── core/                 # 數位孿生核心模型和業務邏輯
│   └── simulator/            # 模擬感測器數據的腳本
├── frontend/
│   ├── web/                  # React 前端應用程式
│   │   ├── components/       # UI 元件 (3D 視覺化, 設定面板)
│   │   ├── context/          # 數據狀態管理 (DigitalTwinContext)
│   │   └── assets/models/    # .glb 3D 模型檔案
│   └── swift/                # Swift/SwiftUI 應用程式
└── docs/                     # 專案文件、藍圖等
    └── floorplan_2d.png      # 2D 平面圖
```
