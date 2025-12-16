//建立房間設定介面 (2D UI)

import React, { useState, useEffect } from 'react';
import { useDigitalTwin } from '../../context/DigitalTwinContext';

const RoomSettings = ({ roomId }) => {
  const { homeData, updateRoomSettings } = useDigitalTwin();
  const room = homeData.rooms.find(r => r.id === roomId);

  const [name, setName] = useState(room.name);
  const [owner, setOwner] = useState(room.owner);
  
  // 確保在選擇不同房間時狀態會同步更新
  useEffect(() => {
    if (room) {
      setName(room.name);
      setOwner(room.owner);
    }
  }, [room]);

  if (!room) return <div className="p-4">找不到房間配置。</div>;

  const handleSave = () => {
    updateRoomSettings(roomId, { name, owner });
    alert(`房間 ${name} 的設定已儲存！`);
  };

  // 暫時忽略感測器設定的細節，先著重於名稱和擁有者
  return (
    <div className="bg-white p-6 rounded-lg shadow-xl space-y-4">
      <h3 className="text-xl font-bold text-gray-800 border-b pb-2">房間設定: {room.name}</h3>
      
      {/* 房間名稱設定 */}
      <div>
        <label className="block text-sm font-medium text-gray-700">房間名稱</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        />
      </div>

      {/* 房間擁有者設定 */}
      <div>
        <label className="block text-sm font-medium text-gray-700">房間擁有者/使用者</label>
        <input
          type="text"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          className="mt-1 block w-full p-2 border border-gray-300 rounded-md"
        />
      </div>

      {/* 顯示感測器列表（配置細節留白） */}
      <h4 className="text-lg font-semibold mt-4">已配置感測器 ({room.sensorConfig.length} 個)</h4>
      <ul className="list-disc list-inside space-y-1 text-sm text-gray-600">
        {room.sensorConfig.map(sensor => (
          <li key={sensor.id}>
            **{sensor.type}** ({sensor.id}) - <span className={`font-bold ${sensor.status === 'closed' || sensor.status === 'normal' || sensor.status === 'idle' ? 'text-green-600' : 'text-red-600'}`}>{sensor.status}</span>
            {/* 這裡可以加入 "編輯感測器" 按鈕，留待未來擴充 */}
          </li>
        ))}
      </ul>

      <button
        onClick={handleSave}
        className="mt-6 w-full px-4 py-2 bg-indigo-600 text-white font-medium rounded-md hover:bg-indigo-700"
      >
        儲存設定
      </button>
    </div>
  );
};

export default RoomSettings;