#!/usr/bin/env python3
"""
BLE DALI 조명 제어 모듈
라즈베리파이에서 BLE를 통해 DALI 조명을 제어
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
import time
from datetime import datetime
import statistics
from collections import defaultdict, deque
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.device_config import get_device_config

try:
    import bleak
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    logging.warning("bleak 모듈이 설치되지 않음 - 시뮬레이션 모드로 동작")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BLEDALIController:
    """BLE DALI 조명 제어 클래스"""
    
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.device_address: Optional[str] = None
        # Nordic UART Service (NUS) UUID
        self.service_uuid = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
        self.characteristic_uuid_rx = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write
        self.characteristic_uuid_tx = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify
        self.is_connected = False
        self.simulation_mode = not BLEAK_AVAILABLE
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        
        # 시스템 사양 캐시 (Zero 2W 호환성)
        self._system_memory_mb = None
        self._is_zero2w = None
        self._low_memory_threshold = 1000  # 1GB 미만은 저사양으로 판단
        
        # 성능 측정 및 최적화
        self.performance_stats = {
            'command_times': defaultdict(deque),  # 명령별 응답 시간
            'connection_times': deque(maxlen=50),  # 연결 시간
            'scan_times': deque(maxlen=20),       # 스캔 시간
            'total_commands': 0,
            'failed_commands': 0,
            'avg_response_time': 0.0,
            'last_performance_report': time.time()
        }
        
        # 연결 풀링 및 최적화
        self.connection_pool = {}  # MAC 주소별 연결 캐시
        self.connection_locks = {}  # 동시 연결 방지용 락
        self.last_command_time = {}  # 장치별 마지막 명령 시간
        self.min_command_interval = 0.2 if self._is_zero2w else 0.1  # Zero 2W는 더 긴 간격

        # 전송 동시성 제한(1:M 안정화) 및 ACK 대기 설정
        self._is_low_memory_system()  # 내부 플래그 초기화(_is_zero2w 등)
        self.max_concurrent_commands = 2 if self._is_zero2w else 4
        try:
            import asyncio as _asyncio
            self.global_semaphore = _asyncio.Semaphore(self.max_concurrent_commands)
        except Exception:
            self.global_semaphore = None
        # 각 (mac, driver_id)별 ACK Future 저장소
        self.pending_acks: dict = {}
        # mac별 notify 시작 여부
        self.notify_started = set()
        # ACK 타임아웃 (초)
        self.ack_timeout = 1.2 if self._is_zero2w else 0.8
        
        # 명령 큐 (Zero 2W 최적화)
        self.command_queue = asyncio.Queue(maxsize=10)
        self.queue_processor_task = None
        self.cleanup_task = None
        
        # 동적 장치 설정 로드
        self.device_config = get_device_config()
        self.dali_device_map = self.device_config.get_device_map()
        
        # 그룹별 DALI 매핑을 설정에서 로드
        self.group_dali_map = {}
        for group_id in self.device_config.get_active_groups():
            self.group_dali_map[group_id] = self.device_config.get_group_devices(group_id)
        
        # 설정에서 명령 간격 가져오기
        config_interval = self.device_config.get_command_interval()
        if config_interval > 0:
            self.min_command_interval = config_interval
        
        logger.info(f"장치 설정 로드 완료: {len(self.dali_device_map)}개 장치")
        logger.info(f"활성 그룹: {self.device_config.get_active_groups()}")
        logger.info(f"그룹 매핑: {self.group_dali_map}")
        logger.info(f"명령 간격: {self.min_command_interval}초")
        
        # 릴레이 제어 (GPIO 핀 매핑)
        self.relay_pins = {
            'relay_A': 18,  # G1 전원 릴레이
            'relay_B': 19,  # G2 전원 릴레이  
            'relay_C': 20,  # G3 전원 릴레이
            'relay_D': 21,  # G4 전원 릴레이
            'relay_E': 22   # G0 릴레이
        }
        
        # GPIO 초기화
        self._init_gpio()
        
        logger.info(f"BLE DALI 컨트롤러 초기화 완료 (시뮬레이션 모드: {self.simulation_mode})")
    
    def _calc_checksum(self, data_bytes: List[int]) -> int:
        """체크섬 계산"""
        return sum(data_bytes) & 0xFF
    
    def _build_packet(self, driver_id: int, brightness: int) -> bytes:
        """DALI 제어 패킷 생성"""
        group_id = 0xA0  # 고정값
        packet = [group_id, driver_id, 0x01, 1, brightness]  # 명령 코드=0x01(밝기 설정)
        packet.append(self._calc_checksum(packet))
        return bytes(packet)
    
    def _notification_handler(self, sender, data):
        """BLE 응답 처리"""
        data_list = list(data)
        if len(data_list) >= 5:
            group_id = data_list[0]
            driver_id = data_list[1]
            result_code = data_list[2]
            status_val = data_list[3]
            success = result_code == 0x01
            logger.info(f"[BLE 응답] 그룹:0x{group_id:02X} 드라이버:0x{driver_id:02X} "
                       f"결과:{'성공' if success else '실패'} 상태값:0x{status_val:02X}")
            return success
        else:
            logger.warning(f"[BLE 응답 RAW] {data_list}")
            return False

    def _notification_handler_factory(self, mac_address: str):
        """mac별로 ACK Future를 해제하는 notify 핸들러 생성"""
        def _handler(sender, data):
            try:
                data_list = list(data)
                if len(data_list) >= 3:
                    driver_id = data_list[1]
                    result_code = data_list[2]
                    success = (result_code == 0x01)
                    key = (mac_address, int(driver_id))
                    fut = self.pending_acks.get(key)
                    if fut and not fut.done():
                        fut.set_result(success)
            except Exception as e:
                logger.warning(f"notify 처리 중 예외(mac={mac_address}): {e}")
        return _handler
    
    def _init_gpio(self):
        """GPIO 초기화 - Zero 2W 호환성 강화"""
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # GPIO 핀 접근 권한 체크
            for pin in self.relay_pins.values():
                try:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.LOW)  # 초기값: OFF
                except Exception as pin_error:
                    logger.warning(f"GPIO 핀 {pin} 설정 실패: {pin_error}")
                    continue
                
            logger.info("GPIO 초기화 완료")
            
        except ImportError:
            logger.warning("RPi.GPIO 모듈이 없음 - 릴레이 시뮬레이션 모드")
            # 대안 라이브러리 시도
            try:
                import gpiod
                logger.info("gpiod 라이브러리 사용 가능 - 대안으로 활용 가능")
            except ImportError:
                logger.info("GPIO 제어가 완전히 시뮬레이션 모드로 동작")
                
        except PermissionError:
            logger.error("GPIO 접근 권한 없음 - gpio 그룹에 사용자 추가 필요")
            logger.info("해결 방법: sudo usermod -a -G gpio $USER")
            
        except Exception as e:
            logger.error(f"GPIO 초기화 실패: {e}")
            logger.info("시뮬레이션 모드로 계속 진행")
    
    async def scan_devices(self, timeout: int = 10) -> List[str]:
        """BLE 장치 스캔 (실제 DALI MAC 주소 확인)"""
        start_time = time.time()
        
        if self.simulation_mode:
            logger.info("시뮬레이션 모드: 가상 BLE 장치 반환")
            await asyncio.sleep(0.1)  # 시뮬레이션 지연
            self._record_performance('scan', time.time() - start_time)
            return ["SIMULATION_DEVICE"]
        
        try:
            logger.info(f"BLE 장치 스캔 시작 ({timeout}초)...")
            devices = await BleakScanner.discover(timeout=timeout)
            
            found_devices = []
            # 실제 DALI 장치 MAC 주소 목록
            known_mac_addresses = {device_info["mac"] for device_info in self.dali_device_map.values() 
                                 if not device_info["mac"].startswith("AA:BB:CC:DD:EE")}
            
            for device in devices:
                if device.address in known_mac_addresses:
                    found_devices.append(device.address)
                    # MAC 주소로 DALI ID 찾기
                    dali_id = next((dali_id for dali_id, info in self.dali_device_map.items() 
                                  if info["mac"] == device.address), "Unknown")
                    logger.info(f"DALI 장치 발견: {dali_id} ({device.address}) - {device.name or 'Unknown'}")
            
            if found_devices:
                logger.info(f"총 {len(found_devices)}개의 실제 DALI 장치 발견")
            else:
                logger.warning("실제 DALI 장치를 찾을 수 없음 - 알려진 MAC 주소와 일치하는 장치 없음")
            
            # 성능 측정 기록
            self._record_performance('scan', time.time() - start_time)
            return found_devices
            
        except Exception as e:
            logger.error(f"BLE 스캔 실패: {e}")
            self._record_performance('scan', time.time() - start_time, success=False)
            return []
    
    async def connect(self, device_address: Optional[str] = None) -> bool:
        """BLE 장치 연결 상태 확인 - Zero 2W 호환성 강화"""
        if self.simulation_mode:
            logger.info("시뮬레이션 모드: 가상 연결 성공")
            self.is_connected = True
            return True
        
        try:
            self.connection_attempts += 1
            
            # BlueZ 서비스 상태 체크 (Zero 2W에서 중요)
            try:
                import subprocess
                result = subprocess.run(['systemctl', 'is-active', 'bluetooth'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode != 0:
                    logger.warning("Bluetooth 서비스가 비활성 상태")
                    logger.info("해결 방법: sudo systemctl start bluetooth")
            except Exception:
                pass  # 서비스 체크 실패해도 계속 진행
            
            # 실제 DALI 장치 스캔하여 연결 가능성 확인
            logger.info("실제 DALI 장치 연결 가능성 확인 중...")
            try:
                devices = await asyncio.wait_for(self.scan_devices(timeout=5), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("BLE 스캔 시간 초과")
                devices = []
            
            if not devices or devices == ["SIMULATION_DEVICE"]:
                logger.warning("연결 가능한 실제 DALI 장치를 찾을 수 없음")
                if self.connection_attempts >= self.max_connection_attempts:
                    logger.info("최대 연결 시도 횟수 초과 - 시뮬레이션 모드로 전환")
                    self.simulation_mode = True
                    self.is_connected = True
                    return True
                return False
            
            # 개별 장치 연결 방식이므로 연결 상태를 True로 설정
            # 실제 연결은 send_dali_command에서 개별적으로 수행
            self.is_connected = True
            self.connection_attempts = 0  # 연결 성공 시 카운터 리셋
            
            logger.info(f"DALI 장치 연결 준비 완료 - {len(devices)}개 장치 발견")
            return True
            
        except Exception as e:
            logger.error(f"BLE 연결 확인 실패: {e}")
            
            # 특정 에러에 대한 자세한 안내
            if "org.freedesktop.DBus.Error" in str(e):
                logger.info("DBus 오류 - BlueZ 서비스 재시작을 시도해보세요")
                logger.info("해결 방법: sudo systemctl restart bluetooth")
            elif "Permission denied" in str(e):
                logger.info("권한 오류 - bluetooth 그룹에 사용자 추가 필요")
                logger.info("해결 방법: sudo usermod -a -G bluetooth $USER")
            
            if self.connection_attempts >= self.max_connection_attempts:
                logger.info("최대 연결 시도 횟수 초과 - 시뮬레이션 모드로 전환")
                self.simulation_mode = True
                self.is_connected = True
                return True
            return False
    
    def get_connection_status(self) -> dict:
        """연결 상태 정보 반환"""
        return {
            'is_connected': self.is_connected,
            'simulation_mode': self.simulation_mode,
            'device_address': self.device_address,
            'connection_attempts': self.connection_attempts,
            'hardware_available': BLEAK_AVAILABLE
        }

    async def health_check(self, scan_timeout: int = 3, include_scan: bool = True) -> Dict[str, Any]:
        """BLE-DALI 헬스체크

        - 기본 상태(연결/시뮬레이션/디바이스 맵)와 옵션으로 BLE 스캔 결과를 반환
        - 스캔은 빠르게 진행하며, 알려진 DALI MAC 존재 여부를 함께 리포트
        """
        result: Dict[str, Any] = {
            'hardware_available': BLEAK_AVAILABLE,
            'simulation_mode': self.simulation_mode,
            'is_connected': self.is_connected,
            'known_devices_total': len(getattr(self, 'dali_device_map', {}) or {}),
            'active_groups': list(getattr(self, 'active_groups', []) or []),
        }

        # 디바이스 맵 요약
        known_map: Dict[str, Dict[str, Any]] = getattr(self, 'dali_device_map', {}) or {}
        result['known_devices'] = [
            {
                'dali_id': dali_id,
                'mac': info.get('mac'),
                'driver_id': info.get('driver_id'),
            }
            for dali_id, info in known_map.items()
        ]

        # 옵션 스캔 수행
        if include_scan:
            if not BLEAK_AVAILABLE:
                result['scan'] = {
                    'performed': False,
                    'reason': 'bleak_not_available'
                }
            elif self.simulation_mode:
                result['scan'] = {
                    'performed': False,
                    'reason': 'simulation_mode'
                }
            else:
                try:
                    devices = await BleakScanner.discover(timeout=scan_timeout)
                    discovered = [
                        {
                            'name': getattr(d, 'name', None),
                            'address': getattr(d, 'address', None),
                        }
                        for d in devices
                    ]
                    known_macs = {info.get('mac') for info in known_map.values() if info.get('mac')}
                    discovered_known = [d for d in discovered if d.get('address') in known_macs]
                    result['scan'] = {
                        'performed': True,
                        'timeout_sec': scan_timeout,
                        'discovered_total': len(discovered),
                        'discovered_known_total': len(discovered_known),
                        'discovered_known': discovered_known,
                    }
                except Exception as e:
                    logger.error(f"헬스체크 스캔 실패: {e}")
                    result['scan'] = {
                        'performed': False,
                        'error': str(e),
                    }

        # 간단한 이슈 요약
        issues: List[str] = []
        if not result['simulation_mode'] and not result['is_connected']:
            issues.append('ble_not_connected')
        scan_info = result.get('scan') or {}
        if scan_info.get('performed') and scan_info.get('discovered_known_total', 0) == 0 and not result['simulation_mode']:
            issues.append('known_devices_not_found_in_scan')
        result['issues'] = issues

        return result
    
    def _record_performance(self, operation: str, duration: float, success: bool = True):
        """성능 데이터 기록"""
        if operation == 'command':
            self.performance_stats['command_times'][operation].append(duration)
            if len(self.performance_stats['command_times'][operation]) > 100:
                self.performance_stats['command_times'][operation].popleft()
            
            self.performance_stats['total_commands'] += 1
            if not success:
                self.performance_stats['failed_commands'] += 1
                
            # 평균 응답 시간 계산
            all_times = list(self.performance_stats['command_times'][operation])
            if all_times:
                self.performance_stats['avg_response_time'] = statistics.mean(all_times)
        
        elif operation == 'connection':
            self.performance_stats['connection_times'].append(duration)
        elif operation == 'scan':
            self.performance_stats['scan_times'].append(duration)
    
    def get_performance_stats(self) -> dict:
        """성능 통계 반환"""
        stats = {}
        
        # 명령 응답 시간 통계
        if self.performance_stats['command_times']:
            all_command_times = []
            for times in self.performance_stats['command_times'].values():
                all_command_times.extend(times)
            
            if all_command_times:
                stats['command_response'] = {
                    'avg_ms': round(statistics.mean(all_command_times) * 1000, 2),
                    'min_ms': round(min(all_command_times) * 1000, 2),
                    'max_ms': round(max(all_command_times) * 1000, 2),
                    'count': len(all_command_times)
                }
        
        # 연결 시간 통계
        if self.performance_stats['connection_times']:
            connection_times = list(self.performance_stats['connection_times'])
            stats['connection'] = {
                'avg_ms': round(statistics.mean(connection_times) * 1000, 2),
                'min_ms': round(min(connection_times) * 1000, 2),
                'max_ms': round(max(connection_times) * 1000, 2),
                'count': len(connection_times)
            }
        
        # 스캔 시간 통계
        if self.performance_stats['scan_times']:
            scan_times = list(self.performance_stats['scan_times'])
            stats['scan'] = {
                'avg_ms': round(statistics.mean(scan_times) * 1000, 2),
                'min_ms': round(min(scan_times) * 1000, 2),
                'max_ms': round(max(scan_times) * 1000, 2),
                'count': len(scan_times)
            }
        
        # 전체 통계
        stats['overall'] = {
            'total_commands': self.performance_stats['total_commands'],
            'failed_commands': self.performance_stats['failed_commands'],
            'success_rate': round((self.performance_stats['total_commands'] - 
                                 self.performance_stats['failed_commands']) / 
                                max(self.performance_stats['total_commands'], 1) * 100, 2)
        }
        
        return stats
    
    def get_performance_bottlenecks(self) -> List[str]:
        """성능 병목 지점 분석"""
        bottlenecks = []
        stats = self.get_performance_stats()
        
        # 응답 시간 체크
        if 'command_response' in stats:
            avg_ms = stats['command_response']['avg_ms']
            if avg_ms > 2000:  # 2초 이상
                bottlenecks.append(f"명령 응답 시간이 느림: {avg_ms}ms (권장: <1000ms)")
            elif avg_ms > 1000:  # 1초 이상
                bottlenecks.append(f"명령 응답 시간 개선 필요: {avg_ms}ms")
        
        # 연결 시간 체크
        if 'connection' in stats:
            avg_ms = stats['connection']['avg_ms']
            if avg_ms > 5000:  # 5초 이상
                bottlenecks.append(f"BLE 연결 시간이 느림: {avg_ms}ms (권장: <3000ms)")
        
        # 성공률 체크
        if 'overall' in stats:
            success_rate = stats['overall']['success_rate']
            if success_rate < 90:
                bottlenecks.append(f"명령 성공률이 낮음: {success_rate}% (권장: >95%)")
        
        # Zero 2W 특화 체크
        if self._is_zero2w:
            if 'command_response' in stats and stats['command_response']['avg_ms'] > 1500:
                bottlenecks.append("Zero 2W에서 응답 시간이 권장값 초과 (1500ms)")
        
        return bottlenecks
    
    async def _get_or_create_connection(self, mac_address: str) -> Optional[BleakClient]:
        """연결 풀에서 연결 가져오기 또는 새로 생성"""
        if self.simulation_mode:
            return None
        
        # 연결 락 생성 (동시 연결 방지)
        if mac_address not in self.connection_locks:
            self.connection_locks[mac_address] = asyncio.Lock()
        
        async with self.connection_locks[mac_address]:
            # 기존 연결이 유효한지 확인
            if mac_address in self.connection_pool:
                client = self.connection_pool[mac_address]
                if client.is_connected:
                    return client
                else:
                    # 연결이 끊어진 경우 제거
                    del self.connection_pool[mac_address]
            
            # 새 연결 생성
            try:
                client = BleakClient(mac_address)
                await client.connect()
                
                if client.is_connected:
                    self.connection_pool[mac_address] = client
                    # notify는 1회만 시작하여 재사용(오버헤드 절감)
                    try:
                        if mac_address not in self.notify_started:
                            await client.start_notify(self.characteristic_uuid_tx, self._notification_handler_factory(mac_address))
                            self.notify_started.add(mac_address)
                    except Exception as e:
                        logger.warning(f"notify 시작 실패(mac={mac_address}): {e}")
                    logger.info(f"새 BLE 연결 생성: {mac_address}")
                    return client
                else:
                    logger.error(f"BLE 연결 실패: {mac_address}")
                    return None
                    
            except Exception as e:
                logger.error(f"BLE 연결 생성 실패 {mac_address}: {e}")
                return None
    
    async def _cleanup_connections(self):
        """사용하지 않는 연결 정리"""
        current_time = time.time()
        to_remove = []
        
        for mac_address, client in self.connection_pool.items():
            # 5분 이상 사용하지 않은 연결 정리
            last_used = self.last_command_time.get(mac_address, 0)
            if current_time - last_used > 300:  # 5분
                to_remove.append(mac_address)
        
        for mac_address in to_remove:
            try:
                client = self.connection_pool[mac_address]
                if client.is_connected:
                    try:
                        # notify 종료
                        if mac_address in self.notify_started:
                            await client.stop_notify(self.characteristic_uuid_tx)
                            self.notify_started.discard(mac_address)
                    except Exception:
                        pass
                    await client.disconnect()
                del self.connection_pool[mac_address]
                logger.info(f"비활성 연결 정리: {mac_address}")
            except Exception as e:
                logger.warning(f"연결 정리 실패 {mac_address}: {e}")
    
    async def _wait_for_command_interval(self, mac_address: str):
        """명령 간격 조절 (Zero 2W 최적화)"""
        if mac_address in self.last_command_time:
            elapsed = time.time() - self.last_command_time[mac_address]
            if elapsed < self.min_command_interval:
                wait_time = self.min_command_interval - elapsed
                await asyncio.sleep(wait_time)
        
        self.last_command_time[mac_address] = time.time()
    
    async def disconnect(self):
        """BLE 장치 연결 해제 및 연결 풀 정리"""
        if self.simulation_mode:
            logger.info("시뮬레이션 모드: 가상 연결 해제")
            self.is_connected = False
            return
        
        try:
            # 연결 풀의 모든 연결 해제
            for mac_address, client in list(self.connection_pool.items()):
                try:
                    if client.is_connected:
                        try:
                            if mac_address in self.notify_started:
                                await client.stop_notify(self.characteristic_uuid_tx)
                                self.notify_started.discard(mac_address)
                        except Exception:
                            pass
                        await client.disconnect()
                        logger.info(f"BLE 연결 해제: {mac_address}")
                except Exception as e:
                    logger.warning(f"연결 해제 실패 {mac_address}: {e}")
            
            # 연결 풀 정리
            self.connection_pool.clear()
            self.connection_locks.clear()
            self.last_command_time.clear()
            
            self.is_connected = False
            logger.info("모든 DALI 장치 연결 해제 완료")
            
        except Exception as e:
            logger.error(f"BLE 연결 해제 실패: {e}")
    
    async def send_dali_command(self, dali_id: str, brightness: int) -> bool:
        """DALI 조명 제어 명령 전송 (개별 장치별 BLE 연결)"""
        start_time = time.time()
        success = False
        
        try:
            if dali_id not in self.dali_device_map:
                logger.error(f"알 수 없는 DALI ID: {dali_id}")
                return False
        
            # 밝기값 검증 (0-100 -> 0-254 변환, DALI 프로토콜 맞춤)
            brightness = max(0, min(100, brightness))
            dali_brightness = int(brightness * 254 / 100)
            
            device_info = self.dali_device_map[dali_id]
            mac_address = device_info["mac"]
            driver_id = device_info["driver_id"]
            
            if self.simulation_mode:
                logger.info(f"시뮬레이션: DALI {dali_id} ({mac_address}) 밝기 {brightness}% (0x{dali_brightness:02X}) 설정")
                await asyncio.sleep(0.05)  # 실제 전송 시뮬레이션 (최적화)
                success = True
            
            # 실제 장치가 A1, A2, A3가 아닌 경우 임시 MAC이므로 시뮬레이션 처리
            elif mac_address.startswith("AA:BB:CC:DD:EE"):
                logger.info(f"임시 MAC 주소 - 시뮬레이션: DALI {dali_id} 밝기 {brightness}%")
                success = True
            
            else:
                # 동시성 윈도 제한
                if self.global_semaphore:
                    async with self.global_semaphore:
                        success = await self._send_with_ack(mac_address, driver_id, dali_brightness, dali_id, brightness)
                else:
                    success = await self._send_with_ack(mac_address, driver_id, dali_brightness, dali_id, brightness)
            
        except Exception as e:
            logger.error(f"DALI {dali_id} ({mac_address}) 명령 전송 실패: {e}")
            success = False
        
        finally:
            # 성능 데이터 기록
            duration = time.time() - start_time
            self._record_performance('command', duration, success)
            
            # 주기적 성능 보고 (10초마다)
            if time.time() - self.performance_stats['last_performance_report'] > 10:
                self._log_performance_report()
                self.performance_stats['last_performance_report'] = time.time()
        
        return success

    async def _send_with_ack(self, mac_address: str, driver_id: int, dali_brightness: int, dali_id: str, ui_brightness: int) -> bool:
        """notify 기반 ACK를 기다리며 전송"""
        # 최적화된 연결 풀 사용
        await self._wait_for_command_interval(mac_address)
        client = await self._get_or_create_connection(mac_address)
        if not client:
            logger.error(f"DALI {dali_id} ({mac_address}) BLE 연결 실패")
            return False
        try:
            # 패킷 생성 및 전송
            packet = self._build_packet(driver_id, dali_brightness)
            logger.info(f"[전송] DALI {dali_id} ({mac_address}) → {list(packet)}")
            # ACK Future 준비(동일 key 기존 대체)
            loop = asyncio.get_running_loop()
            key = (mac_address, int(driver_id))
            fut = loop.create_future()
            self.pending_acks[key] = fut
            await client.write_gatt_char(self.characteristic_uuid_rx, packet)
            try:
                ok = await asyncio.wait_for(fut, timeout=self.ack_timeout)
                if ok:
                    logger.info(f"DALI {dali_id} 밝기 {ui_brightness}% 설정 ACK 수신")
                    return True
                else:
                    logger.warning(f"DALI {dali_id} 밝기 {ui_brightness}% NACK")
                    return False
            except asyncio.TimeoutError:
                logger.warning(f"DALI {dali_id} ACK 타임아웃({self.ack_timeout}s)")
                return False
            finally:
                # 사용된 Future 정리
                if self.pending_acks.get(key) is fut:
                    self.pending_acks.pop(key, None)
        except Exception as cmd_error:
            logger.error(f"DALI {dali_id} 명령 전송 중 오류: {cmd_error}")
            if mac_address in self.connection_pool:
                try:
                    await self.connection_pool[mac_address].disconnect()
                except Exception:
                    pass
                self.connection_pool.pop(mac_address, None)
            return False
    
    def _log_performance_report(self):
        """성능 보고서 로깅"""
        stats = self.get_performance_stats()
        bottlenecks = self.get_performance_bottlenecks()
        
        if 'command_response' in stats:
            logger.info(f"[성능] 평균 응답시간: {stats['command_response']['avg_ms']}ms, "
                       f"성공률: {stats['overall']['success_rate']}%")
        
        if bottlenecks:
            logger.warning(f"[성능 병목] {', '.join(bottlenecks)}")
    
    def reload_device_config(self):
        """장치 설정 다시 로드"""
        try:
            if self.device_config.reload_if_changed():
                # 설정이 변경된 경우 매핑 업데이트
                old_device_count = len(self.dali_device_map)
                self.dali_device_map = self.device_config.get_device_map()
                
                # 그룹 매핑 업데이트
                self.group_dali_map = {}
                for group_id in self.device_config.get_active_groups():
                    self.group_dali_map[group_id] = self.device_config.get_group_devices(group_id)
                
                # 명령 간격 업데이트
                config_interval = self.device_config.get_command_interval()
                if config_interval > 0:
                    self.min_command_interval = config_interval
                
                new_device_count = len(self.dali_device_map)
                logger.info(f"장치 설정 다시 로드됨: {old_device_count} → {new_device_count}개 장치")
                logger.info(f"활성 그룹: {self.device_config.get_active_groups()}")
                
                return True
            return False
            
        except Exception as e:
            logger.error(f"장치 설정 다시 로드 실패: {e}")
            return False
    
    def start_optimization_tasks(self):
        """최적화 백그라운드 태스크 시작"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.info("연결 정리 백그라운드 태스크 시작")
    
    async def _periodic_cleanup(self):
        """주기적 연결 정리 백그라운드 태스크"""
        try:
            while True:
                await asyncio.sleep(60)  # 1분마다 실행
                if not self.simulation_mode:
                    await self._cleanup_connections()
        except asyncio.CancelledError:
            logger.info("연결 정리 태스크 종료")
        except Exception as e:
            logger.error(f"연결 정리 태스크 오류: {e}")
    
    def set_relay(self, relay_name: str, state: bool) -> bool:
        """릴레이 제어"""
        if relay_name not in self.relay_pins:
            logger.error(f"알 수 없는 릴레이: {relay_name}")
            return False
        
        try:
            import RPi.GPIO as GPIO
            pin = self.relay_pins[relay_name]
            GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            logger.info(f"릴레이 {relay_name} {'ON' if state else 'OFF'} 설정 완료")
            return True
        except ImportError:
            logger.info(f"시뮬레이션: 릴레이 {relay_name} {'ON' if state else 'OFF'}")
            return True
        except Exception as e:
            logger.error(f"릴레이 {relay_name} 제어 실패: {e}")
            return False
    
    def _is_low_memory_system(self) -> bool:
        """저사양 시스템 여부 판단 (Zero 2W 호환성)"""
        if self._system_memory_mb is None:
            try:
                # /proc/meminfo에서 총 메모리 읽기
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            # KB를 MB로 변환
                            memory_kb = int(line.split()[1])
                            self._system_memory_mb = memory_kb // 1024
                            break
                
                # 라즈베리파이 모델 확인
                try:
                    with open('/proc/device-tree/model', 'r') as f:
                        model = f.read().strip('\x00')
                        self._is_zero2w = 'Zero 2' in model
                        if self._is_zero2w:
                            logger.info(f"라즈베리파이 Zero 2W 감지됨 - 메모리: {self._system_memory_mb}MB")
                except:
                    self._is_zero2w = False
                    
            except Exception as e:
                logger.warning(f"시스템 메모리 정보 읽기 실패: {e}")
                # 기본값으로 저사양 시스템으로 가정
                self._system_memory_mb = 512
                self._is_zero2w = True
        
        # Zero 2W이거나 1GB 미만이면 저사양 시스템
        is_low_memory = (self._is_zero2w or 
                        self._system_memory_mb < self._low_memory_threshold)
        
        if is_low_memory:
            logger.debug(f"저사양 시스템 모드 - 메모리: {self._system_memory_mb}MB, Zero2W: {self._is_zero2w}")
        
        return is_low_memory
    
    async def control_group(self, group_id: str, brightness: int) -> bool:
        """그룹 조명 제어"""
        if group_id == 'G0':
            # G0는 릴레이 제어
            return self.set_relay('relay_E', brightness > 0)
        
        if group_id not in self.group_dali_map:
            logger.error(f"알 수 없는 그룹: {group_id}")
            return False
        
        # 해당 그룹의 모든 DALI 조명 제어 (병렬 처리 최적화)
        dali_lights = self.group_dali_map[group_id]
        
        # 시스템 사양에 따른 적응형 처리 (Zero 2W 호환성)
        if self._is_low_memory_system():
            # 저사양 시스템: 순차 처리 (메모리 절약)
            logger.info(f"저사양 시스템 감지 - 순차 처리 모드: {group_id}")
            results = []
            for dali_id in dali_lights:
                result = await self.send_dali_command(dali_id, brightness)
                results.append(result)
        else:
            # 고사양 시스템: 병렬 처리 (성능 우선)
            logger.info(f"고사양 시스템 - 병렬 처리 모드: {group_id}")
            tasks = [self.send_dali_command(dali_id, brightness) for dali_id in dali_lights]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 성공 개수 계산
        success_count = sum(1 for result in results if result is True)
        
        # 그룹 릴레이도 제어
        relay_map = {'G1': 'relay_A', 'G2': 'relay_B', 'G3': 'relay_C', 'G4': 'relay_D'}
        if group_id in relay_map:
            self.set_relay(relay_map[group_id], brightness > 0)
        
        success = success_count == len(dali_lights)
        if success:
            logger.info(f"그룹 {group_id} 밝기 {brightness}% 설정 완료 (병렬 처리 - {len(dali_lights)}개 조명)")
        else:
            logger.warning(f"그룹 {group_id} 일부 조명 제어 실패 ({success_count}/{len(dali_lights)})")
            # 실패한 조명들 상세 로깅
            for i, result in enumerate(results):
                if result is not True:
                    failed_dali_id = dali_lights[i]
                    logger.error(f"  → {failed_dali_id} 제어 실패: {result if isinstance(result, Exception) else 'Unknown error'}")
        
        return success
    
    async def control_individual_light(self, light_id: str, brightness: int) -> bool:
        """개별 조명 제어"""
        # light_id 형식: G1-A, G1-B, G1-C 등을 DALLA1, DALLA2, DALLA3로 변환
        group_id = light_id.split('-')[0]
        light_index = light_id.split('-')[1]
        
        # 매핑 테이블
        dali_map = {
            'G1': {'A': 'DALLA1', 'B': 'DALLA2', 'C': 'DALLA3'},
            'G2': {'A': 'DALLB1', 'B': 'DALLB2', 'C': 'DALLB3'},
            'G3': {'A': 'DALLC1', 'B': 'DALLC2', 'C': 'DALLC3'},
            'G4': {'A': 'DALLD1', 'B': 'DALLD2', 'C': 'DALLD3'}
        }
        
        if group_id not in dali_map or light_index not in dali_map[group_id]:
            logger.error(f"알 수 없는 조명 ID: {light_id}")
            return False
        
        dali_id = dali_map[group_id][light_index]
        return await self.send_dali_command(dali_id, brightness)
    
    async def get_temperature(self) -> float:
        """온도 센서 값 읽기"""
        if self.simulation_mode:
            # 시뮬레이션: 22-26도 사이 랜덤값
            import random
            temp = 22.0 + random.random() * 4.0
            return round(temp, 1)
        
        try:
            # 실제 온도 센서 읽기 로직 구현
            # 예: DS18B20, DHT22 등
            return 23.5  # 임시값
        except Exception as e:
            logger.error(f"온도 센서 읽기 실패: {e}")
            return 23.0
    
    def cleanup(self):
        """리소스 정리"""
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
            logger.info("GPIO 정리 완료")
        except:
            pass

# 전역 컨트롤러 인스턴스
ble_controller = BLEDALIController()

async def init_hardware():
    """하드웨어 초기화"""
    success = await ble_controller.connect()
    if success:
        logger.info("하드웨어 초기화 완료")
    else:
        logger.warning("BLE 연결 실패 - 시뮬레이션 모드로 동작")
    return success

async def cleanup_hardware():
    """하드웨어 정리"""
    await ble_controller.disconnect()
    ble_controller.cleanup()
    logger.info("하드웨어 정리 완료")

if __name__ == "__main__":
    async def test():
        # 테스트 코드
        print("=== BLE DALI 컨트롤러 테스트 ===")
        
        await init_hardware()
        
        # 장치 스캔 테스트
        print("\n1. 장치 스캔 테스트")
        devices = await ble_controller.scan_devices(timeout=3)
        print(f"발견된 장치: {devices}")
        
        # 개별 조명 제어 테스트 (실제 MAC 주소가 있는 A1, A2, A3)
        print("\n2. 개별 조명 제어 테스트")
        await ble_controller.send_dali_command('DALLA1', 75)
        await asyncio.sleep(1)
        await ble_controller.send_dali_command('DALLA2', 50)
        await asyncio.sleep(1)
        await ble_controller.send_dali_command('DALLA3', 25)
        await asyncio.sleep(1)
        
        # 그룹 제어 테스트
        print("\n3. 그룹 제어 테스트")
        await ble_controller.control_group('G1', 80)
        await asyncio.sleep(2)
        
        # 개별 조명 제어 테스트 (웹 UI 형식)
        print("\n4. 웹 UI 형식 개별 조명 제어 테스트")
        await ble_controller.control_individual_light('G1-A', 60)
        await asyncio.sleep(1)
        
        # G0 릴레이 테스트
        print("\n5. G0 릴레이 테스트")
        await ble_controller.control_group('G0', 100)
        await asyncio.sleep(1)
        await ble_controller.control_group('G0', 0)
        
        # 연결 상태 확인
        print("\n6. 연결 상태 확인")
        status = ble_controller.get_connection_status()
        print(f"연결 상태: {status}")
        
        await cleanup_hardware()
        print("\n=== 테스트 완료 ===")
    
    asyncio.run(test())