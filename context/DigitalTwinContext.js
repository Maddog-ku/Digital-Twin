// 管理住家數據和狀態的核心 Context
import React, { createContext, useState, useContext } from 'react';

// 初始數據結構：代表住家的數位孿生
const initialHomeData = {
  // 基礎資訊
  name: "智慧安全示範屋",
  // 房間列表：每個房間都有設定和感測器
  rooms: [
    {
      id: 'room_a',
      name: '主臥室 (User A)',
      owner: 'User A',
      sensorConfig: [
        { id: 'motion_01', type: 'PIR', status: 'idle', location: [1.5, 0.2, 0] }, // location: 3D 坐標
        { id: 'temp_01', type: 'Temperature', status: '26.5°C', location: [-1.5, 0.2, 0.5] }
      ]
    },
    {
      id: 'room_b',
      name: '客廳 (公共區域)',
      owner: 'Common',
      sensorConfig: [
        { id: 'door_main', type: 'DoorContact', status: 'closed', location: [3, 0.5, 0] },
        { id: 'smoke_01', type: 'Smoke', status: 'normal', location: [0, 2.5, 0] }
      ]
    }
  ],
};

const DigitalTwinContext = createContext();

export const useDigitalTwin = () => useContext(DigitalTwinContext);

export const DigitalTwinProvider = ({ children }) => {
  const [homeData, setHomeData] = useState(initialHomeData);

  // 動作：更新特定房間的設定
  const updateRoomSettings = (roomId, newSettings) => {
    setHomeData(prevData => ({
      ...prevData,
      rooms: prevData.rooms.map(room => 
        room.id === roomId ? { ...room, ...newSettings } : room
      )
    }));
  };

  // 動作：更新特定感測器的狀態 (這將用於串接模型或模擬)
  const updateSensorStatus = (roomId, sensorId, newStatus) => {
    setHomeData(prevData => ({
      ...prevData,
      rooms: prevData.rooms.map(room => 
        room.id === roomId
          ? {
              ...room,
              sensorConfig: room.sensorConfig.map(sensor => 
                sensor.id === sensorId ? { ...sensor, status: newStatus } : sensor
              )
            }
          : room
      )
    }));
  };

  return (
    <DigitalTwinContext.Provider value={{ homeData, updateRoomSettings, updateSensorStatus }}>
      {children}
    </DigitalTwinContext.Provider>
  );
};