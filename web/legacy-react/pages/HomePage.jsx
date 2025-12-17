import React, { useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useDigitalTwin } from '../context/DigitalTwinContext';
import RoomSettings from '../components/Settings/RoomSettings';
import Home3D from '../components/Visualizer/Home3D'; // 假設您已實現 Home3D

const HomePage = () => {
  const { homeData } = useDigitalTwin();
  const [selectedRoomId, setSelectedRoomId] = useState(homeData.rooms[0]?.id);
  const selectedRoom = homeData.rooms.find(r => r.id === selectedRoomId);

  return (
    <div className="flex h-screen bg-gray-50">
      {/* 左側：3D 數位孿生視覺化 */}
      <div className="w-3/5 bg-gray-200 relative">
        <h1 className="absolute top-4 left-4 text-2xl font-extrabold text-indigo-700 z-10">
          {homeData.name} - 數位孿生
        </h1>
        <Canvas camera={{ position: [5, 5, 5], fov: 60 }} className="h-full w-full">
          <ambientLight intensity={0.5} />
          <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} castShadow />
          
          {/* 渲染住家 3D 模型和感測器 */}
          <Home3D onRoomClick={setSelectedRoomId} selectedRoomId={selectedRoomId} /> 
          
          <OrbitControls />
        </Canvas>
        <div className="absolute bottom-4 left-4 bg-black bg-opacity-50 text-white p-2 rounded text-sm z-10">
            點擊房間模型或感測器以選取和檢視設定。
        </div>
      </div>

      {/* 右側：2D 設定與狀態資訊面板 */}
      <div className="w-2/5 p-8 overflow-y-auto">
        <h2 className="text-3xl font-bold mb-6 text-gray-900">安全監控與設定</h2>
        
        {/* 房間選擇器 */}
        <div className="mb-6">
          <label className="block text-lg font-medium text-gray-700 mb-2">選擇要設定的房間:</label>
          <select 
            value={selectedRoomId} 
            onChange={(e) => setSelectedRoomId(e.target.value)}
            className="w-full p-3 border border-gray-300 rounded-lg shadow-sm focus:ring-indigo-500 focus:border-indigo-500"
          >
            {homeData.rooms.map(room => (
              <option key={room.id} value={room.id}>
                {room.name} ({room.owner})
              </option>
            ))}
          </select>
        </div>

        {/* 房間設定元件 */}
        {selectedRoom && <RoomSettings roomId={selectedRoom.id} />}
      </div>
    </div>
  );
};

export default HomePage;

