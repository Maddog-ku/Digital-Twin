import sys
import random

try:
    import ezdxf
    from ezdxf import units
except ImportError:
    print("❌ ezdxf not installed. Run: pip install ezdxf")
    sys.exit(1)

def setup_layers(doc):
    """設定標準 CAD 圖層與顏色"""
    layers = [
        ("WALL", 7),       # 白色/黑色 (牆)
        ("COLUMN", 2),     # 黃色 (柱子)
        ("DOOR", 6),       # 洋紅 (門)
        ("FURNITURE", 1),  # 紅色 (家具)
        ("TEXT", 3),       # 綠色 (文字)
        ("DIMENSION", 4)   # 青色 (標註 - 預留)
    ]
    for name, color in layers:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)

def create_furniture_block(doc):
    """創建一個 '辦公桌組合' 的 Block (圖塊)，以便重複調用"""
    if "OFFICE_DESK" in doc.blocks:
        return
        
    block = doc.blocks.new(name="OFFICE_DESK")
    
    # 桌子 (矩形)
    block.add_lwpolyline([(0, 0), (1.6, 0), (1.6, 0.8), (0, 0.8)], close=True, dxfattribs={'layer': 'FURNITURE'})
    
    # 椅子 (圓形)
    block.add_circle((0.8, -0.4), radius=0.25, dxfattribs={'layer': 'FURNITURE'})
    
    # 電腦螢幕 (線段)
    block.add_line((0.4, 0.2), (1.2, 0.2), dxfattribs={'layer': 'FURNITURE'})

def draw_room(msp, x, y, w, h, room_id):
    """在指定位置繪製一個房間，包含牆壁、柱子、門、家具與文字"""
    
    # 1. 繪製牆壁 (使用 Polyline)
    # 留出門的缺口 (假設門在下方牆壁的中間)
    door_width = 0.9
    door_start = x + (w / 2) - (door_width / 2)
    door_end = x + (w / 2) + (door_width / 2)

    # 左牆
    msp.add_line((x, y), (x, y+h), dxfattribs={'layer': 'WALL'})
    # 上牆
    msp.add_line((x, y+h), (x+w, y+h), dxfattribs={'layer': 'WALL'})
    # 右牆
    msp.add_line((x+w, y+h), (x+w, y), dxfattribs={'layer': 'WALL'})
    # 下牆 (分兩段，中間留門)
    msp.add_line((x, y), (door_start, y), dxfattribs={'layer': 'WALL'})
    msp.add_line((door_end, y), (x+w, y), dxfattribs={'layer': 'WALL'})

    # 2. 繪製門 (弧線示意)
    msp.add_arc(
        center=(door_start, y),
        radius=door_width,
        start_angle=0,
        end_angle=90,
        dxfattribs={'layer': 'DOOR'}
    )

    # 3. 繪製柱子 (角落的填充矩形)
    # 使用 Solid (實心填充) 代表結構柱
    col_size = 0.4
    msp.add_solid(
        [(x, y+h), (x+col_size, y+h), (x+col_size, y+h-col_size), (x, y+h-col_size)],
        dxfattribs={'layer': 'COLUMN'}
    )

    # 4. 插入家具 Block (隨機旋轉或位置微調)
    # 插入兩個辦公位
    msp.add_blockref("OFFICE_DESK", (x + 1, y + 2), dxfattribs={'rotation': 0})
    msp.add_blockref("OFFICE_DESK", (x + w - 2.6, y + 2), dxfattribs={'rotation': 180})

    # 5. 添加房間編號文字
    # --- 修正重點：使用字串 "MIDDLE_CENTER" ---
    msp.add_text(
        f"RM-{room_id}",
        dxfattribs={'layer': 'TEXT', 'height': 0.5}
    ).set_placement((x + w/2, y + h/2), align="MIDDLE_CENTER")

def create_complex_floor_plan():
    filename = "complex_office_plan.dxf"
    
    try:
        doc = ezdxf.new("R2010")
        doc.units = units.M  # 設定單位為公尺
        msp = doc.modelspace()

        # 初始化設定
        setup_layers(doc)
        create_furniture_block(doc)

        # 參數設定
        rows = 6       # 6排
        cols = 8       # 8列
        room_w = 5.0   # 房間寬 5米
        room_h = 4.0   # 房間深 4米
        corridor = 2.0 # 走廊寬度

        print(f"正在生成 {rows * cols} 個房間的複雜平面圖...")

        room_count = 0
        for r in range(rows):
            for c in range(cols):
                room_count += 1
                
                # 計算座標
                x_pos = c * room_w
                
                # 為了製造走廊，每兩排房間中間隔開
                # 邏輯：如果 row 是偶數 (0,2,4)，它是走廊下方的房間
                # 如果 row 是奇數 (1,3,5)，它是走廊上方的房間
                y_offset = (r // 2) * corridor # 累積走廊寬度
                y_pos = r * room_h + y_offset

                draw_room(msp, x_pos, y_pos, room_w, room_h, f"{100+room_count}")

        # 繪製建築外框 (包圍所有房間)
        total_w = cols * room_w
        total_h = rows * room_h + (rows // 2) * corridor
        
        # 外牆加粗 (使用 Polyline width)
        outer_points = [
            (-0.5, -0.5),
            (total_w + 0.5, -0.5),
            (total_w + 0.5, total_h + 0.5),
            (-0.5, total_h + 0.5)
        ]
        msp.add_lwpolyline(
            outer_points, 
            format="xy", 
            close=True, 
            dxfattribs={'layer': 'WALL', 'const_width': 0.1} # const_width 設定線寬
        )

        doc.saveas(filename)
        print(f"✅ 成功建立複雜 DXF: {filename}")
        print(f"包含: {room_count} 個房間, 圖塊, 填充柱, 文字標籤與分層結構。")

    except Exception as e:
        print(f"❌ 建立 DXF 時發生錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_complex_floor_plan()