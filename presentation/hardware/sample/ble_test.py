import asyncio
from bleak import BleakClient

# ===== 12개 장치 MAC 주소 및 DriverID 매핑 =====
DEVICE_MAP = {
    "DALI_A1": {"mac": "E4:B3:23:A2:F6:F2", "driver_id": 0x01},
    "DALI_A2": {"mac": "E4:B3:23:A2:D1:EE", "driver_id": 0x02},
    "DALI_A3": {"mac": "E4:B3:23:A2:D1:CE", "driver_id": 0x03},
    "DALI_B1": {"mac": "AA:BB:CC:DD:EE:04", "driver_id": 0x04},
    "DALI_B2": {"mac": "AA:BB:CC:DD:EE:05", "driver_id": 0x05},
    "DALI_B3": {"mac": "AA:BB:CC:DD:EE:06", "driver_id": 0x06},
    "DALI_C1": {"mac": "AA:BB:CC:DD:EE:07", "driver_id": 0x07},
    "DALI_C2": {"mac": "AA:BB:CC:DD:EE:08", "driver_id": 0x08},
    "DALI_C3": {"mac": "AA:BB:CC:DD:EE:09", "driver_id": 0x09},
    "DALI_D1": {"mac": "AA:BB:CC:DD:EE:0A", "driver_id": 0x0A},
    "DALI_D2": {"mac": "AA:BB:CC:DD:EE:0B", "driver_id": 0x0B},
    "DALI_D3": {"mac": "AA:BB:CC:DD:EE:0C", "driver_id": 0x0C},
}

# ===== UUID =====
CHARACTERISTIC_UUID_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write
CHARACTERISTIC_UUID_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify

# ===== 체크섬 =====
def calc_checksum(data_bytes):
    return sum(data_bytes) & 0xFF

# ===== 패킷 빌드 =====
def build_packet(driver_id, brightness):
    group_id = 0xA0  # 그룹 ID는 고정값(필요 시 변경 가능)
    packet = [group_id, driver_id, 0x01, 1, brightness]  # 명령 코드=0x01(밝기 설정)
    packet.append(calc_checksum(packet))
    return bytes(packet)

# ===== 응답 처리 =====
def notification_handler(sender, data):
    data_list = list(data)
    if len(data_list) >= 5:
        group_id = data_list[0]
        driver_id = data_list[1]
        result_code = data_list[2]
        status_val = data_list[3]
        print(f"[응답] 그룹:0x{group_id:02X} 드라이버:0x{driver_id:02X} "
              f"결과:{'성공' if result_code == 0x01 else '실패'} "
              f"상태값:0x{status_val:02X}")
    else:
        print(f"[응답 RAW] {data_list}")

# ===== 장치 제어 =====
async def send_command(device_name, brightness):
    if device_name not in DEVICE_MAP:
        print(f"❌ 잘못된 장치명: {device_name}")
        return

    mac = DEVICE_MAP[device_name]["mac"]
    driver_id = DEVICE_MAP[device_name]["driver_id"]

    try:
        async with BleakClient(mac) as client:
            if not client.is_connected:
                print(f"❌ {device_name} ({mac}) BLE 연결 실패")
                return

            await client.start_notify(CHARACTERISTIC_UUID_TX, notification_handler)

            packet = build_packet(driver_id, brightness)
            print(f"[전송] {device_name} ({mac}) → {list(packet)}")
            await client.write_gatt_char(CHARACTERISTIC_UUID_RX, packet)

            await asyncio.sleep(0.5)
            await client.stop_notify(CHARACTERISTIC_UUID_TX)

    except Exception as e:
        print(f"❌ {device_name} ({mac}) 통신 오류: {e}")

# ===== 메인 루프 =====
async def control_loop():
    while True:
        user_input = input("\n형식: 장치명 밝기(0~254), q=종료: ").strip()
        if user_input.lower() == "q":
            break

        parts = user_input.split()
        if len(parts) != 2:
            print("❌ 입력 형식 오류")
            continue

        device_name = parts[0].upper()
        try:
            brightness_value = int(parts[1])
        except ValueError:
            print("❌ 밝기값은 숫자만 입력")
            continue

        if not (0 <= brightness_value <= 254):
            print("❌ 밝기 범위 오류 (0~254)")
            continue

        await send_command(device_name, brightness_value)