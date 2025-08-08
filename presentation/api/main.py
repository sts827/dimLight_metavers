#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스마트 스위치 디밍 웹 애플리케이션
라즈베리파이 키오스크 모드용 웹 서버
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import sys
import logging
import asyncio
import threading
from datetime import datetime

# 인코딩 설정 (Python 3.7+)
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 하드웨어 제어 모듈 임포트
try:
    from presentation.hardware.ble_controller import ble_controller, init_hardware, cleanup_hardware
    HARDWARE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"하드웨어 모듈 임포트 실패: {e} - 시뮬레이션 모드로 동작")
    ble_controller = None
    HARDWARE_AVAILABLE = False

# 디바이스 설정 모듈 임포트
try:
    from core.device_config import get_device_config
    DEVICE_CONFIG_AVAILABLE = True
except ImportError as e:
    logging.warning(f"디바이스 설정 모듈 임포트 실패: {e} - 하드코딩된 설정 사용")
    DEVICE_CONFIG_AVAILABLE = False

# 임시로 enum 정의 (import 문제 해결)
class ControlMode:
    AUTO = "auto"
    MANUAL = "manual"

class WeekDay:
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7

# Flask 앱 설정
app = Flask(__name__, 
           template_folder='../ui/templates',
           static_folder='../ui/static')
app.config['SECRET_KEY'] = 'smart_switch_dimming_secret_key'

# Socket.IO 설정 (보안 및 성능 최적화)
socketio = SocketIO(app, 
                   cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"],
                   async_mode='threading',
                   ping_timeout=10,
                   ping_interval=5,
                   max_http_buffer_size=1000000,
                   allow_upgrades=True,
                   compression=True)

# 로깅 설정 (회전 파일 핸들러 + 콘솔)
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("smart_switch")
logger.setLevel(logging.INFO)

log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'log')
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, 'app.log')

if not logger.handlers:
    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# 비동기 이벤트 루프 설정
loop = None
loop_thread = None

def run_async_in_loop(coro):
    """비동기 함수를 별도 스레드의 이벤트 루프에서 실행"""
    if loop and not loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=5.0)
        except Exception as e:
            logger.error(f"비동기 작업 실행 실패: {e}")
            return False
    return False

def load_dynamic_groups():
    """device_map.json에서 동적으로 그룹 정보를 로드"""
    try:
        if not DEVICE_CONFIG_AVAILABLE:
            logger.warning("디바이스 설정 모듈 사용 불가 - 하드코딩된 그룹 사용")
            return get_fallback_groups()
        
        config = get_device_config()
        if not config:
            logger.warning("디바이스 설정 로드 실패 - 하드코딩된 그룹 사용")
            return get_fallback_groups()
        
        groups = []
        lights = []
        
        # 활성 그룹만 처리
        active_groups = config.get('active_groups', ['G1'])
        
        # G0 그룹 (릴레이) - 항상 포함
        groups.append({
            'id': 'G0', 
            'name': 'G0 (릴레이)', 
            'brightness': None, 
            'is_on': True, 
            'type': 'on_off_only'
        })
        lights.append({
            'id': 'G0-A', 
            'name': 'G0-A (relay_E)', 
            'brightness': None, 
            'is_on': True, 
            'group_id': 'G0', 
            'type': 'on_off_only'
        })
        
        # 활성 그룹들 처리
        group_names = {
            'G1': 'G1 (DALI A)',
            'G2': 'G2 (DALI B)', 
            'G3': 'G3 (DALI C)'
        }
        
        for group_id in active_groups:
            if group_id == 'G0':
                continue  # 이미 추가됨
                
            group_name = group_names.get(group_id, f'{group_id} (DALI)')
            
            # 그룹 추가
            groups.append({
                'id': group_id,
                'name': group_name,
                'brightness': 1 if group_id == 'G1' else 50,  # G1은 1% (1단계), 나머지는 50%
                'is_on': True,  # 전체 조명 제어 ON 상태로 모든 그룹 켜짐
                'type': 'dimmable'
            })
            
            # 해당 그룹의 개별 장치들 추가
            if group_id in config.get('groups', {}):
                device_list = config['groups'][group_id]
                for i, device_id in enumerate(device_list):
                    device_info = config.get('dali_devices', {}).get(device_id, {})
                    device_name = device_info.get('name', f'{device_id}')
                    
                    lights.append({
                        'id': f'{group_id}-{chr(65+i)}',  # G1-A, G1-B, G1-C
                        'name': f'{group_id}-{chr(65+i)} ({device_name})',
                        'brightness': 1 if group_id == 'G1' else 50,
                        'is_on': True,
                        'group_id': group_id
                    })
        
        logger.info(f"동적 그룹 로드 완료: {len(groups)}개 그룹, {len(lights)}개 개별 장치")
        logger.info(f"활성 그룹: {active_groups}")
        
        return groups, lights
        
    except Exception as e:
        logger.error(f"동적 그룹 로드 실패: {e} - 하드코딩된 그룹 사용")
        return get_fallback_groups()

def get_fallback_groups():
    """하드코딩된 기본 그룹 (fallback)"""
    groups = [
        {'id': 'G0', 'name': 'G0 (릴레이)', 'brightness': None, 'is_on': True, 'type': 'on_off_only'},
        {'id': 'G1', 'name': 'G1 (DALI A)', 'brightness': 1, 'is_on': True, 'type': 'dimmable'},  # 1단계 (1%)
    ]
    
    lights = [
        # G1 그룹 (DALI A그룹 - DALLA1, DALLA2, DALLA3)
        {'id': 'G1-A', 'name': 'G1-A (A1 조명)', 'brightness': 1, 'is_on': True, 'group_id': 'G1'},  # 1단계 (1%)
        {'id': 'G1-B', 'name': 'G1-B (A2 조명)', 'brightness': 1, 'is_on': True, 'group_id': 'G1'},  # 1단계 (1%)
        {'id': 'G1-C', 'name': 'G1-C (A3 조명)', 'brightness': 1, 'is_on': True, 'group_id': 'G1'},  # 1단계 (1%)
        # G0 그룹 (릴레이 E - relay_E)
        {'id': 'G0-A', 'name': 'G0-A (relay_E)', 'brightness': None, 'is_on': True, 'group_id': 'G0', 'type': 'on_off_only'}
    ]
    
    return groups, lights

def detect_system_capabilities():
    """시스템 사양 감지 및 최적화 설정"""
    import os
    import psutil
    
    # 메모리 정보
    total_ram = psutil.virtual_memory().total // (1024 * 1024)  # MB
    
    # Zero 2W 감지
    is_zero2w = False
    try:
        if os.path.exists('/proc/device-tree/model'):
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip('\x00')
                if 'Zero 2' in model:
                    is_zero2w = True
                    logger.info(f"Raspberry Pi Zero 2W 감지됨 (RAM: {total_ram}MB)")
    except:
        pass
    
    # 메모리 제약 환경 최적화
    if total_ram <= 512 or is_zero2w:
        logger.info("메모리 제약 환경 감지 - 최적화 모드 활성화")
        # Python GC 최적화
        import gc
        gc.set_threshold(700, 10, 10)  # 더 자주 GC 실행
        
        # Flask 설정 최적화
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # 캐시 시간 단축
        app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB 제한
        
        # 로깅 레벨 완만화(Zero 2W 등)
        logger.setLevel(logging.INFO)
        return True
    
    return False

def start_event_loop():
    """백그라운드에서 이벤트 루프 실행 - Zero 2W 최적화"""
    global loop
    
    # 시스템 사양 감지
    memory_constrained = detect_system_capabilities()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # 환경 변수 기반 초기화 제어
    skip_hw = os.getenv('SKIP_HARDWARE_INIT', '0').lower() in ('1', 'true', 'yes')
    force_sim = os.getenv('FORCE_SIMULATION', '0').lower() in ('1', 'true', 'yes')
    # 하드웨어 초기화
    if HARDWARE_AVAILABLE and not skip_hw:
        try:
            # 메모리 제약 환경에서는 타임아웃 단축 + 환경변수로 오버라이드
            default_timeout = 10 if memory_constrained else 30
            timeout = float(os.getenv('BLE_INIT_TIMEOUT', default_timeout))
            # 강제 시뮬레이션 모드
            if force_sim and ble_controller:
                try:
                    ble_controller.simulation_mode = True
                except Exception:
                    pass
            success = loop.run_until_complete(
                asyncio.wait_for(init_hardware(), timeout=timeout)
            )
            
            if success:
                logger.info("하드웨어 초기화 완료")
                app_state['hardware_status'] = ble_controller.get_connection_status()
            else:
                logger.warning("하드웨어 연결 실패 - 시뮬레이션 모드로 동작")
                app_state['hardware_status'] = ble_controller.get_connection_status()
                
        except asyncio.TimeoutError:
            logger.warning(f"하드웨어 초기화 시간 초과 ({timeout}초) - 시뮬레이션 모드로 전환")
            app_state['hardware_status'] = {
                'is_connected': False,
                'simulation_mode': True,
                'device_address': None,
                'connection_attempts': 0,
                'hardware_available': False,
                'error': 'Hardware initialization timeout'
            }
        except Exception as e:
            logger.error(f"하드웨어 초기화 실패: {e}")
            app_state['hardware_status'] = {
                'is_connected': False,
                'simulation_mode': True,
                'device_address': None,
                'connection_attempts': 0,
                'hardware_available': False,
                'error': str(e)
            }
    else:
        logger.info("하드웨어 모듈 사용 불가 - 순수 시뮬레이션 모드")
        app_state['hardware_status'] = {
            'is_connected': False,
            'simulation_mode': True,
            'device_address': None,
            'connection_attempts': 0,
            'hardware_available': False,
            'error': 'Hardware modules not available'
        }
    
    # 메모리 제약 환경에서는 더 자주 정리
    if memory_constrained:
        import gc
        gc.collect()
    
    # 이벤트 루프 실행
    loop.run_forever()


@app.route('/api/system/memory')
def get_system_memory():
    """시스템 메모리/CPU 간단 상태"""
    try:
        import psutil
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        return jsonify({
            'success': True,
            'memory': {
                'total': vm.total,
                'available': vm.available,
                'used': vm.used,
                'percent': vm.percent,
            },
            'cpu_percent': cpu,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"시스템 메모리 상태 조회 실패: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 동적으로 그룹 및 조명 정보 로드
dynamic_groups, dynamic_lights = load_dynamic_groups()

# 임시 상태 저장 (실제로는 데이터베이스나 파일 시스템 사용)
app_state = {
    'current_mode': ControlMode.MANUAL,
    'sensor_data': {
        'power_consumption': 85.2,
        'temperature': 22.5,
        'humidity': 45.0
    },
    'total_control': {
        'is_on': True,
        'description': '전체 조명 제어'
    },
    'groups': dynamic_groups,
    'lights': dynamic_lights,
    'macros': [
    ],
    'schedules': [],
    'device_info': {
        'device_name': 'Smart Switch Dimmer',
        'version': '1.0.0',
        'serial_number': 'SSD-001',
        'manufacturer': 'SM_allione',
        'ip_address': '192.168.1.140'
    },
    'hardware_status': {
        'is_connected': False,
        'simulation_mode': True,
        'device_address': None,
        'connection_attempts': 0,
        'hardware_available': False,
        'error': 'Not initialized'
    }
}


@app.route('/')
def index():
    """메인 페이지 - 현재 모드에 따라 리다이렉트"""
    if app_state['current_mode'] == ControlMode.AUTO:
        return render_template('landing_auto.html', state=app_state)
    else:
        return render_template('landing_manual.html', state=app_state)


@app.route('/landing_auto')
def landing_auto():
    """자동 모드 대기 화면"""
    return render_template('landing_auto.html', state=app_state)


@app.route('/landing_manual')
def landing_manual():
    """수동 모드 대기 화면"""
    return render_template('landing_manual.html', state=app_state)


@app.route('/main_group')
def main_group():
    """그룹 제어 화면"""
    if app_state['current_mode'] == ControlMode.AUTO:
        return redirect(url_for('landing_auto'))
    return render_template('main_group.html', state=app_state)


@app.route('/main_personal')
def main_personal():
    """개별 제어 화면"""
    if app_state['current_mode'] == ControlMode.AUTO:
        return redirect(url_for('landing_auto'))
    return render_template('main_personal.html', state=app_state)


@app.route('/main_settings')
def main_settings():
    """설정 메인 화면"""
    return render_template('main_settings.html', state=app_state)


@app.route('/settings_mode')
def settings_mode():
    """모드 전환 설정 화면"""
    return render_template('settings_mode.html', state=app_state)


@app.route('/settings_device')
def settings_device():
    """장치 정보 설정 화면"""
    return render_template('settings_device.html', state=app_state)


@app.route('/settings_groups')
def settings_groups():
    """그룹 관리 설정 화면"""
    return render_template('settings_groups.html', state=app_state)


@app.route('/main_macro')
def main_macro():
    """매크로 설정 화면"""
    if app_state['current_mode'] == ControlMode.AUTO:
        return redirect(url_for('landing_auto'))
    return render_template('main_macro.html', state=app_state)

@app.route('/macro_setting')
def macro_setting():
    """매크로 설정 화면"""
    return render_template('macro_setting.html', state=app_state)

# =============================
# BLE 디버깅/헬스체크 API
# =============================

@app.route('/api/ble/health', methods=['GET'])
def ble_health():
    """BLE 상태/스캔 요약 (include_scan=true 쿼리로 스캔 수행)"""
    try:
        include_scan = str(request.args.get('include_scan', 'false')).lower() in ('1', 'true', 'yes')
        scan_timeout = int(request.args.get('scan_timeout', 3))
        result = run_async_in_loop(ble_controller.health_check(scan_timeout=scan_timeout, include_scan=include_scan))
        return jsonify({'success': True, 'health': result})
    except Exception as e:
        logger.error(f"BLE health 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/ble/stats', methods=['GET'])
def ble_stats():
    """BLE 성능 통계/병목 요약"""
    try:
        stats = ble_controller.get_performance_stats()
        bottlenecks = ble_controller.get_performance_bottlenecks()
        extra = {
            'is_connected': getattr(ble_controller, 'is_connected', False),
            'simulation_mode': getattr(ble_controller, 'simulation_mode', True),
            'max_concurrent_commands': getattr(ble_controller, 'max_concurrent_commands', None),
            'ack_timeout': getattr(ble_controller, 'ack_timeout', None),
        }
        return jsonify({'success': True, 'stats': stats, 'bottlenecks': bottlenecks, 'extra': extra})
    except Exception as e:
        logger.error(f"BLE stats 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/ble/config', methods=['PUT'])
def ble_config():
    """BLE 런타임 튜닝(ack_timeout, max_concurrent_commands, min_command_interval)"""
    try:
        data = request.get_json(force=True)
        updated = {}
        if 'ack_timeout' in data:
            ble_controller.ack_timeout = float(data['ack_timeout'])
            updated['ack_timeout'] = ble_controller.ack_timeout
        if 'max_concurrent_commands' in data:
            val = int(data['max_concurrent_commands'])
            ble_controller.max_concurrent_commands = val
            import asyncio as _asyncio
            ble_controller.global_semaphore = _asyncio.Semaphore(val)
            updated['max_concurrent_commands'] = val
        if 'min_command_interval' in data:
            ble_controller.min_command_interval = float(data['min_command_interval'])
            updated['min_command_interval'] = ble_controller.min_command_interval
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        logger.error(f"BLE config 업데이트 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/ble/simulation', methods=['PUT'])
def ble_toggle_simulation():
    """시뮬레이션 모드 토글 { enable: true|false }"""
    try:
        data = request.get_json(force=True)
        enable = bool(data.get('enable', True))
        ble_controller.simulation_mode = enable
        # 시뮬레이션 모드 켜면 연결된 것으로 간주
        if enable:
            ble_controller.is_connected = True
        return jsonify({'success': True, 'simulation_mode': ble_controller.simulation_mode})
    except Exception as e:
        logger.error(f"BLE simulation 토글 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/ble/command', methods=['POST'])
def ble_test_command():
    """개별 DALI 명령 테스트(dali_id, brightness)"""
    try:
        data = request.get_json(force=True)
        dali_id = data.get('dali_id')
        brightness = int(data.get('brightness', 0))
        from time import time as _now
        t0 = _now()
        ok = run_async_in_loop(ble_controller.send_dali_command(dali_id, brightness))
        dt = (_now() - t0) * 1000.0
        return jsonify({'success': bool(ok), 'took_ms': round(dt, 1)})
    except Exception as e:
        logger.error(f"BLE test command 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/ble/group', methods=['POST'])
def ble_test_group():
    """그룹 밝기 테스트(group_id, brightness)"""
    try:
        data = request.get_json(force=True)
        group_id = data.get('group_id')
        brightness = int(data.get('brightness', 0))
        from time import time as _now
        t0 = _now()
        ok = run_async_in_loop(ble_controller.control_group(group_id, brightness))
        dt = (_now() - t0) * 1000.0
        return jsonify({'success': bool(ok), 'took_ms': round(dt, 1)})
    except Exception as e:
        logger.error(f"BLE group 테스트 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/main_schedule')
def main_schedule():
    """스케줄 설정 화면"""
    return render_template('main_schedule.html', state=app_state)


# API 엔드포인트들
@app.route('/api/state')
def get_state():
    """현재 상태 조회"""
    return jsonify(app_state)


@app.route('/api/groups')
def get_groups():
    """그룹 목록 조회"""
    try:
        return jsonify({
            'success': True,
            'groups': app_state['groups'],
            'total_control': app_state['total_control']
        })
    except Exception as e:
        logger.error(f"그룹 조회 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/lights')
def get_lights():
    """개별 조명 목록 조회"""
    try:
        return jsonify({
            'success': True,
            'lights': app_state['lights'],
            'groups': app_state['groups']
        })
    except Exception as e:
        logger.error(f"개별 조명 조회 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/mode', methods=['POST'])
def set_mode():
    """모드 변경"""
    data = request.get_json()
    mode = data.get('mode')
    
    if mode in ['auto', 'manual']:
        app_state['current_mode'] = ControlMode.AUTO if mode == 'auto' else ControlMode.MANUAL
        
        # Socket.IO 제거됨 - API 응답으로 충분
        
        return jsonify({'success': True, 'message': f'{mode} 모드로 변경되었습니다'})
    
    return jsonify({'success': False, 'message': '잘못된 모드입니다'}), 400


def _set_brightness_internal(group_id=None, light_id=None, brightness=0):
    """내부 밝기 제어 로직 (Flask API와 Socket.IO에서 공통 사용)"""
    try:
        if brightness < 0 or brightness > 100:
            raise ValueError("밝기는 0-100 사이의 값이어야 합니다")
        
        if app_state['current_mode'] == ControlMode.AUTO:
            raise Exception("자동 모드에서는 조작할 수 없습니다")
        
        # 하드웨어 제어 성공 여부
        hardware_success = True
        
        # 개별 조명 밝기 업데이트
        if light_id:
            if HARDWARE_AVAILABLE and ble_controller:
                # 실제 하드웨어 제어 시도
                hardware_success = run_async_in_loop(
                    ble_controller.control_individual_light(light_id, brightness)
                )
                if not hardware_success:
                    logger.warning(f"개별 조명 {light_id} 하드웨어 제어 실패 - 메모리 상태만 업데이트")
            else:
                logger.info(f"하드웨어 미연결 - 개별 조명 {light_id} 시뮬레이션 모드")
                hardware_success = False
            
            # 하드웨어 제어 성공 여부와 관계없이 메모리 상태 업데이트
            for light in app_state['lights']:
                if light['id'] == light_id:
                    light['brightness'] = brightness
                    light['is_on'] = brightness > 0
                    logger.info(f"개별 조명 '{light['name']}' 메모리 상태 {brightness}로 업데이트")
                    break
        
        # 그룹 밝기 업데이트
        if group_id:
            if HARDWARE_AVAILABLE and ble_controller:
                # 실제 하드웨어 제어 시도
                group_hardware_success = run_async_in_loop(
                    ble_controller.control_group(group_id, brightness)
                )
                if not group_hardware_success:
                    logger.warning(f"그룹 {group_id} 하드웨어 제어 실패 - 메모리 상태만 업데이트")
                    hardware_success = False
            else:
                logger.info(f"하드웨어 미연결 - 그룹 {group_id} 시뮬레이션 모드")
                hardware_success = False
            
            # 하드웨어 제어 성공 여부와 관계없이 메모리 상태 업데이트
            for group in app_state['groups']:
                if group['id'] == group_id:
                    # G0 그룹은 On/Off만 가능
                    if group_id == 'G0':
                        group['is_on'] = brightness > 0
                        logger.info(f"그룹 '{group['name']}' 메모리 상태 {'ON' if brightness > 0 else 'OFF'}로 업데이트")
                        
                        # G0 그룹의 개별 장비도 On/Off만 업데이트
                        for light in app_state['lights']:
                            if light['group_id'] == group_id:
                                light['is_on'] = brightness > 0
                    else:
                        # G1~G4 그룹은 밝기 조절 가능
                        group['brightness'] = brightness
                        group['is_on'] = brightness > 0
                        logger.info(f"그룹 '{group['name']}' 메모리 상태 밝기 {brightness}로 업데이트")
                        
                        # 해당 그룹의 모든 개별 조명도 함께 업데이트
                        for light in app_state['lights']:
                            if light['group_id'] == group_id:
                                light['brightness'] = brightness
                                light['is_on'] = brightness > 0
                    break
        
        return {'success': True, 'message': '밝기가 조정되었습니다', 'hardware_controlled': hardware_success}
        
    except Exception as e:
        logger.error(f"밝기 조정 실패: {e}")
        return {'success': False, 'message': str(e)}


def _set_total_control_internal(is_on=False):
    """내부 전체 조명 제어 로직 (Flask API와 Socket.IO에서 공통 사용)"""
    try:        
        # 하드웨어 제어 성공 여부 추적
        hardware_success = True
        failed_groups = []
        
        # 모든 그룹에 대해 하드웨어 제어 실행
        if HARDWARE_AVAILABLE and ble_controller:
            for group in app_state['groups']:
                group_id = group['id']
                brightness = 1 if is_on else 0  # ON일 때는 1% (1단계), OFF일 때는 0%
                
                # G0는 릴레이이므로 특별 처리
                if group_id == 'G0':
                    brightness = 100 if is_on else 0
                
                success = run_async_in_loop(
                    ble_controller.control_group(group_id, brightness)
                )
                
                if not success:
                    hardware_success = False
                    failed_groups.append(group_id)
                    logger.warning(f"그룹 {group_id} 하드웨어 제어 실패 - 메모리 상태만 업데이트")
        else:
            logger.info("하드웨어 미연결 - 전체 조명 시뮬레이션 모드")
            hardware_success = False
        
        # 하드웨어 제어 성공 여부와 관계없이 메모리 상태 업데이트
        # 전체 조명 제어 상태 업데이트
        app_state['total_control']['is_on'] = is_on
        
        # 모든 그룹 On/Off 설정
        for group in app_state['groups']:
            group['is_on'] = is_on
            if not is_on:
                # Off일 때는 밝기도 0으로 (G0 제외)
                if group['id'] != 'G0':
                    group['brightness'] = 0
            elif group['id'] != 'G0':
                # ON일 때는 기본 밝기로 설정 (1단계)
                group['brightness'] = 1
        
        # 모든 개별 조명 On/Off 설정
        for light in app_state['lights']:
            light['is_on'] = is_on
            if not is_on and light.get('type') != 'on_off_only':
                # Off일 때는 밝기도 0으로 (G0-A 제외)
                light['brightness'] = 0
            elif is_on and light.get('type') != 'on_off_only':
                # ON일 때는 기본 밝기로 설정 (1단계)
                light['brightness'] = 1
        
        status_msg = f"전체 조명 메모리 상태 {'ON' if is_on else 'OFF'}로 업데이트"
        if failed_groups:
            status_msg += f" (하드웨어 제어 실패: {', '.join(failed_groups)})"
        logger.info(status_msg)
        
        return {
            'success': True, 
            'message': f"전체 조명이 {'켜졌습니다' if is_on else '꺼졌습니다'}" + 
                      (f" (시뮬레이션 모드)" if not hardware_success else ""),
            'hardware_controlled': hardware_success,
            'failed_groups': failed_groups if failed_groups else []
        }
        
    except Exception as e:
        logger.error(f"전체 조명 제어 실패: {e}")
        return {'success': False, 'message': str(e)}


@app.route('/api/brightness', methods=['POST'])
def set_brightness():
    """밝기 조정 API 엔드포인트"""
    data = request.get_json()
    light_id = data.get('light_id')
    group_id = data.get('group_id')
    brightness = data.get('brightness', 0)
    
    # 내부 함수 호출
    result = _set_brightness_internal(group_id=group_id, light_id=light_id, brightness=brightness)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/total-control', methods=['POST'])
def set_total_control():
    """전체 조명 제어 API 엔드포인트"""
    data = request.get_json()
    is_on = data.get('is_on', False)
    
    # 내부 함수 호출
    result = _set_total_control_internal(is_on=is_on)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400



@app.route('/api/sensor')
def get_sensor_data():
    """센서 데이터 조회"""
    try:
        # 실제 온도 센서에서 데이터 읽기
        if HARDWARE_AVAILABLE and ble_controller:
            temperature = run_async_in_loop(ble_controller.get_temperature())
            if temperature:
                app_state['sensor_data']['temperature'] = temperature
        
        # 전력 소모량 계산 (시뮬레이션)
        total_power = 0
        for group in app_state['groups']:
            if group['is_on']:
                if group['id'] == 'G0':
                    total_power += 20  # 릴레이 기본 소모량
                else:
                    brightness = group.get('brightness', 0)
                    # DALI 조명 3개 그룹 * 밝기에 따른 소모량
                    total_power += (brightness / 100) * 30 * 3  # 각 조명당 최대 30W
        
        app_state['sensor_data']['power_consumption'] = round(total_power, 1)
        app_state['sensor_data']['timestamp'] = datetime.now().isoformat()
        
        return jsonify(app_state['sensor_data'])
    except Exception as e:
        logger.error(f"센서 데이터 조회 실패: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/hardware-status')
def get_hardware_status():
    """하드웨어 연결 상태 조회"""
    try:
        # 실시간 하드웨어 상태 업데이트
        if HARDWARE_AVAILABLE and ble_controller:
            current_status = ble_controller.get_connection_status()
            app_state['hardware_status'].update(current_status)
        
        app_state['hardware_status']['timestamp'] = datetime.now().isoformat()
        
        return jsonify({
            'success': True,
            'hardware_status': app_state['hardware_status']
        })
    except Exception as e:
        logger.error(f"하드웨어 상태 조회 실패: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health')
def api_health_check():
    """BLE-DALI 및 시스템 헬스체크

    - 컨트롤러 상태와 옵션 스캔 결과를 반환한다.
    - 서버 부하를 줄이기 위해 스캔 시간은 3초로 고정.
    """
    try:
        if HARDWARE_AVAILABLE and ble_controller:
            health = run_async_in_loop(ble_controller.health_check(scan_timeout=3, include_scan=True))
        else:
            health = {
                'hardware_available': False,
                'simulation_mode': True,
                'is_connected': False,
                'issues': ['hardware_module_unavailable']
            }
        return jsonify({'success': True, 'health': health})
    except Exception as e:
        logger.error(f"헬스체크 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/hardware-reconnect', methods=['POST'])
def reconnect_hardware():
    """하드웨어 재연결 시도"""
    try:
        if not HARDWARE_AVAILABLE:
            return jsonify({
                'success': False, 
                'message': '하드웨어 모듈이 사용 불가능합니다'
            }), 400
        
        if not ble_controller:
            return jsonify({
                'success': False, 
                'message': 'BLE 컨트롤러가 초기화되지 않았습니다'
            }), 400
        
        # 기존 연결 해제
        if ble_controller.is_connected:
            run_async_in_loop(ble_controller.disconnect())
        
        # 재연결 시도
        success = run_async_in_loop(ble_controller.connect())
        
        # 상태 업데이트
        app_state['hardware_status'] = ble_controller.get_connection_status()
        app_state['hardware_status']['timestamp'] = datetime.now().isoformat()
        
        if success:
            message = "하드웨어 재연결 성공"
            if ble_controller.simulation_mode:
                message += " (시뮬레이션 모드)"
        else:
            message = "하드웨어 재연결 실패"
        
        return jsonify({
            'success': success,
            'message': message,
            'hardware_status': app_state['hardware_status']
        })
        
    except Exception as e:
        logger.error(f"하드웨어 재연결 실패: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/system/mode', methods=['GET'])
def get_system_mode():
    """현재 시스템 모드 조회 (manual/auto)"""
    return jsonify({
        'success': True,
        'mode': app_state['current_mode'],
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/system/mode', methods=['PUT'])
def update_system_mode():
    """시스템 모드 변경"""
    try:
        data = request.get_json()
        new_mode = data.get('mode', '').upper()
        
        if new_mode not in ['AUTO', 'MANUAL']:
            return jsonify({
                'success': False,
                'message': '유효하지 않은 모드입니다. AUTO 또는 MANUAL만 가능합니다.'
            }), 400
        
        # 모드 변경
        app_state['current_mode'] = new_mode.lower()
        
        print(f"🔄 시스템 모드 변경: {new_mode}")
        
        return jsonify({
            'success': True,
            'mode': new_mode,
            'message': f'{new_mode} 모드로 변경되었습니다.',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ 모드 변경 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'모드 변경 중 오류가 발생했습니다: {str(e)}'
        }), 500


@app.route('/api/device/info', methods=['GET'])
def get_device_info():
    """장치 정보 조회"""
    device_info = app_state.get('device_info', {})
    
    return jsonify({
        'success': True,
        'device_info': {
            'device_name': device_info.get('device_name', '조명제어기'),
            'version': device_info.get('version', 'V1'),
            'ip_address': device_info.get('ip_address', '192.168.0.1'),
            'serial_number': device_info.get('serial_number', '-'),
            'manufacturer': device_info.get('manufacturer', '(주)올아이원 062-571-1543')
        },
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/device/ip', methods=['PUT'])
def update_device_ip():
    """장치 IP 주소 변경"""
    try:
        data = request.get_json()
        new_ip = data.get('ip_address', '').strip()
        
        if not new_ip:
            return jsonify({
                'success': False,
                'message': 'IP 주소를 입력해주세요.'
            }), 400
        
        # IP 주소 형식 검증 (간단한 정규식)
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        if not re.match(ip_pattern, new_ip):
            return jsonify({
                'success': False,
                'message': 'IP 주소 형식이 올바르지 않습니다.'
            }), 400
        
        # device_info가 없으면 초기화
        if 'device_info' not in app_state:
            app_state['device_info'] = {}
        
        # IP 주소 변경
        old_ip = app_state['device_info'].get('ip_address', '192.168.0.1')
        app_state['device_info']['ip_address'] = new_ip
        
        print(f"🌐 IP 주소 변경: {old_ip} → {new_ip}")
        
        return jsonify({
            'success': True,
            'ip_address': new_ip,
            'message': f'IP 주소가 {new_ip}로 변경되었습니다.',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ IP 주소 변경 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'IP 주소 변경 중 오류가 발생했습니다: {str(e)}'
        }), 500


@app.route('/api/device/groups/reload', methods=['POST'])
def reload_device_groups():
    """디바이스 그룹 설정 다시 로드"""
    try:
        logger.info("디바이스 그룹 설정 다시 로드 요청됨")
        
        # 동적으로 그룹 정보 다시 로드
        new_groups, new_lights = load_dynamic_groups()
        
        # 기존 상태 백업 (활성 상태 유지를 위해)
        old_groups = app_state.get('groups', [])
        old_lights = app_state.get('lights', [])
        
        # 기존 그룹의 상태를 새 그룹에 적용 (가능한 경우)
        for new_group in new_groups:
            for old_group in old_groups:
                if new_group['id'] == old_group['id']:
                    # 기존 상태 유지
                    new_group['is_on'] = old_group.get('is_on', new_group['is_on'])
                    if new_group.get('brightness') is not None and old_group.get('brightness') is not None:
                        new_group['brightness'] = old_group['brightness']
                    break
        
        # 기존 개별 조명의 상태를 새 조명에 적용 (가능한 경우)
        for new_light in new_lights:
            for old_light in old_lights:
                if new_light['id'] == old_light['id']:
                    # 기존 상태 유지
                    new_light['is_on'] = old_light.get('is_on', new_light['is_on'])
                    if new_light.get('brightness') is not None and old_light.get('brightness') is not None:
                        new_light['brightness'] = old_light['brightness']
                    break
        
        # 상태 업데이트
        app_state['groups'] = new_groups
        app_state['lights'] = new_lights
        
        logger.info(f"디바이스 그룹 설정 다시 로드 완료: {len(new_groups)}개 그룹, {len(new_lights)}개 개별 장치")
        
        # Socket.IO로 모든 클라이언트에게 업데이트 알림
        if socketio:
            socketio.emit('groups_reloaded', {
                'groups': new_groups,
                'lights': new_lights,
                'timestamp': datetime.now().isoformat(),
                'message': '그룹 설정이 다시 로드되었습니다'
            })
        
        return jsonify({
            'success': True,
            'message': f'그룹 설정이 다시 로드되었습니다 ({len(new_groups)}개 그룹, {len(new_lights)}개 장치)',
            'groups': new_groups,
            'lights': new_lights,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"디바이스 그룹 설정 다시 로드 실패: {e}")
        return jsonify({
            'success': False,
            'message': f'그룹 설정 다시 로드 중 오류가 발생했습니다: {str(e)}'
        }), 500


@app.route('/api/device/groups/available', methods=['GET'])
def get_available_groups():
    """사용 가능한 모든 그룹 정보 조회 (활성/비활성 포함)"""
    try:
        if not DEVICE_CONFIG_AVAILABLE:
            return jsonify({
                'success': False,
                'message': '디바이스 설정 모듈을 사용할 수 없습니다'
            }), 400
        
        config = get_device_config()
        if not config:
            return jsonify({
                'success': False,
                'message': '디바이스 설정을 로드할 수 없습니다'
            }), 500
        
        all_groups = config.get('groups', {})
        active_groups = config.get('active_groups', ['G1'])
        devices = config.get('dali_devices', {})
        
        result = {
            'all_groups': all_groups,
            'active_groups': active_groups,
            'devices': devices,
            'current_state': {
                'groups': app_state['groups'],
                'lights': app_state['lights']
            }
        }
        
        return jsonify({
            'success': True,
            'data': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"사용 가능한 그룹 정보 조회 실패: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/macros')
def get_macros():
    """매크로 목록 조회"""
    return jsonify({'macros': app_state['macros']})


@app.route('/api/current-settings')
def get_current_settings():
    """현재 조명/그룹 설정값 조회 (매크로 저장용)"""
    try:
        current_settings = {
            'total_control': app_state['total_control'],
            'groups': app_state['groups'],
            'lights': app_state['lights'],
            'timestamp': datetime.now().isoformat()
        }
        return jsonify({'success': True, 'settings': current_settings})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/macros/<int:macro_id>', methods=['POST'])
def save_macro(macro_id):
    """매크로 저장/업데이트"""
    data = request.get_json()
    name = data.get('name', f'MACRO {macro_id}')
    settings = data.get('settings', {})
    
    try:
        if macro_id < 1 or macro_id > 3:
            raise ValueError("매크로 ID는 1-3 사이여야 합니다")
        
        # 매크로 배열 인덱스는 0부터 시작
        index = macro_id - 1
        
        # 리스트 길이 보장 (3슬롯)
        while len(app_state['macros']) < 3:
            app_state['macros'].append(None)

        # 새 매크로 생성 또는 기존 매크로 업데이트
        app_state['macros'][index] = {
            'id': macro_id,
            'name': name,
            'settings': settings
        }
        
        # Socket.IO 제거됨 - API 응답으로 충분
        
        return jsonify({'success': True, 'message': f'{name}이(가) 저장되었습니다'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/macros/<int:macro_id>', methods=['DELETE'])
def delete_macro(macro_id):
    """매크로 삭제"""
    try:
        if macro_id < 1 or macro_id > 3:
            raise ValueError("매크로 ID는 1-3 사이여야 합니다")
        
        # 매크로 배열 인덱스는 0부터 시작
        index = macro_id - 1
        app_state['macros'][index] = None
        
        # Socket.IO 제거됨 - API 응답으로 충분
        
        return jsonify({'success': True, 'message': '매크로가 삭제되었습니다'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/api/macros/<int:macro_id>/execute', methods=['POST'])
def execute_macro(macro_id):
    """매크로 실행 - 저장된 설정값들을 app_state에 적용"""
    try:
        if macro_id < 1 or macro_id > 3:
            raise ValueError("매크로 ID는 1-3 사이여야 합니다")
        
        if app_state['current_mode'] == ControlMode.AUTO:
            raise Exception("자동 모드에서는 매크로를 실행할 수 없습니다")
        
        # 매크로 배열 인덱스는 0부터 시작
        index = macro_id - 1
        macro = app_state['macros'][index]
        
        if not macro or not macro.get('settings'):
            raise ValueError("실행할 매크로가 없거나 설정값이 비어있습니다")
        
        settings = macro['settings']
        applied_changes = []
        
        logger.info(f"매크로 '{macro['name']}' 실행 시작")
        
        # 1. 전체 조명 제어 설정 적용
        if 'total_control' in settings:
            saved_total_control = settings['total_control']
            old_total_state = app_state['total_control']['is_on']
            new_total_state = saved_total_control['is_on']
            app_state['total_control']['is_on'] = new_total_state
            
            if old_total_state != new_total_state:
                applied_changes.append({
                    'type': 'total_control',
                    'id': 'total',
                    'name': '전체 조명 제어',
                    'old_state': old_total_state,
                    'new_state': new_total_state
                })
                logger.info(f"전체 조명 제어: {old_total_state} → {new_total_state}")
        
        # 2. 그룹 설정 적용
        if 'groups' in settings:
            for saved_group in settings['groups']:
                for current_group in app_state['groups']:
                    if current_group['id'] == saved_group['id']:
                        old_brightness = current_group['brightness']
                        current_group['brightness'] = saved_group['brightness']
                        current_group['is_on'] = saved_group['is_on']
                        
                        applied_changes.append({
                            'type': 'group',
                            'id': saved_group['id'],
                            'name': saved_group['name'],
                            'old_brightness': old_brightness,
                            'new_brightness': saved_group['brightness']
                        })
                        
                        logger.info(f"그룹 '{saved_group['name']}' 밝기: {old_brightness} → {saved_group['brightness']}")
                        break
        
        # 3. 개별 조명 설정 적용
        if 'lights' in settings:
            for saved_light in settings['lights']:
                for current_light in app_state['lights']:
                    if current_light['id'] == saved_light['id']:
                        old_brightness = current_light['brightness']
                        current_light['brightness'] = saved_light['brightness']
                        current_light['is_on'] = saved_light['is_on']
                        
                        applied_changes.append({
                            'type': 'light',
                            'id': saved_light['id'],
                            'name': saved_light['name'],
                            'old_brightness': old_brightness,
                            'new_brightness': saved_light['brightness']
                        })
                        
                        logger.info(f"개별 조명 '{saved_light['name']}' 밝기: {old_brightness} → {saved_light['brightness']}")
                        break
        
        # Socket.IO 제거됨 - API 응답으로 충분
        
        # Socket.IO 제거됨 - API 응답으로 충분
        
        logger.info(f"✅ 매크로 '{macro['name']}' 실행 완료 - {len(applied_changes)}개 항목 적용")
        
        return jsonify({
            'success': True, 
            'message': f"매크로 '{macro['name']}'이(가) 실행되었습니다",
            'applied_changes': applied_changes,
            'executed_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ 매크로 실행 실패: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 400


# WebSocket 이벤트 핸들러
# ===== Socket.IO 이벤트 핸들러들 =====

# 연결된 클라이언트 추적
connected_clients = set()

@socketio.on('connect')
def handle_connect():
    """클라이언트 연결 시"""
    session_id = request.sid
    
    # 중복 연결 체크
    if session_id in connected_clients:
        logger.warning(f"⚠️  중복 연결 감지: {session_id}")
        return False  # 연결 거부
    
    connected_clients.add(session_id)
    logger.info(f"🔗 클라이언트 연결됨: {session_id} (총 {len(connected_clients)}개)")
    
    # 현재 상태를 새로 연결된 클라이언트에게 전송
    emit('status_update', {
        'groups': app_state['groups'],
        'lights': app_state['lights'],
        'total_control': app_state['total_control'],
        'hardware_status': app_state['hardware_status']
    })

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제 시"""
    session_id = request.sid
    connected_clients.discard(session_id)
    logger.info(f"🔌 클라이언트 연결 해제됨: {session_id} (남은 {len(connected_clients)}개)")
    logger.info(f"🔌 클라이언트 연결 해제됨: {request.sid}")

@socketio.on('set_brightness')
def handle_set_brightness(data):
    """밝기 설정 Socket.IO 핸들러"""
    try:
        group_id = data.get('group_id')
        light_id = data.get('light_id') 
        brightness = data.get('brightness')
        
        logger.info(f"🔆 Socket.IO 밝기 설정 요청: group_id={group_id}, light_id={light_id}, brightness={brightness}")
        
        if group_id:
            # 즉시 UI 업데이트 (반응성 개선)
            socketio.emit('group_updated', {
                'group_id': group_id,
                'brightness': brightness,
                'is_on': brightness > 0,
                'timestamp': datetime.now().isoformat(),
                'status': 'updating'  # 업데이트 중 상태
            })
            
            # 그룹 밝기 설정 (백그라운드 처리)
            result = _set_brightness_internal(group_id=group_id, brightness=brightness)
            
            # 하드웨어 제어 완료 후 최종 상태 전송
            socketio.emit('group_updated', {
                'group_id': group_id,
                'brightness': brightness,
                'is_on': brightness > 0,
                'timestamp': datetime.now().isoformat(),
                'status': 'completed' if result['success'] else 'failed',
                'hardware_controlled': result.get('hardware_controlled', False)
            })
        elif light_id:
            # 즉시 UI 업데이트 (반응성 개선)
            socketio.emit('light_updated', {
                'light_id': light_id,
                'brightness': brightness,
                'is_on': brightness > 0,
                'timestamp': datetime.now().isoformat(),
                'status': 'updating'  # 업데이트 중 상태
            })
            
            # 개별 조명 밝기 설정 (백그라운드 처리)
            result = _set_brightness_internal(light_id=light_id, brightness=brightness)
            
            # 하드웨어 제어 완료 후 최종 상태 전송
            socketio.emit('light_updated', {
                'light_id': light_id,
                'brightness': brightness,
                'is_on': brightness > 0,
                'timestamp': datetime.now().isoformat(),
                'status': 'completed' if result['success'] else 'failed',
                'hardware_controlled': result.get('hardware_controlled', False)
            })
        
        emit('brightness_response', result)
        
    except Exception as e:
        logger.error(f"❌ Socket.IO 밝기 설정 실패: {str(e)}")
        emit('brightness_response', {'success': False, 'message': str(e)})

@socketio.on('set_total_control')
def handle_set_total_control(data):
    """전체 조명 제어 Socket.IO 핸들러"""
    try:
        is_on = data.get('is_on')
        logger.info(f"🔆 Socket.IO 전체 조명 제어 요청: is_on={is_on}")
        
        result = _set_total_control_internal(is_on=is_on)
        
        if result['success']:
            # 모든 클라이언트에게 전체 상태 업데이트 전송
            socketio.emit('total_control_updated', {
                'is_on': is_on,
                'groups': app_state['groups'],
                'timestamp': datetime.now().isoformat()
            })
        
        emit('total_control_response', result)
        
    except Exception as e:
        logger.error(f"❌ Socket.IO 전체 조명 제어 실패: {str(e)}")
        emit('total_control_response', {'success': False, 'message': str(e)})

@socketio.on('get_status')
def handle_get_status():
    """현재 상태 요청 핸들러"""
    emit('status_update', {
        'groups': app_state['groups'],
        'lights': app_state['lights'], 
        'total_control': app_state['total_control'],
        'hardware_status': app_state['hardware_status']
    })


def create_app():
    """Flask 앱 팩토리"""
    return app


if __name__ == '__main__':
    # 개발 서버 실행
    logger.info("Starting Smart Switch Dimming Web Application")
    logger.info("Access URL: http://localhost:5000")
    
    print("Smart Switch Dimming App initialized")
    print("Kiosk optimizations applied")
    print("접근 모드: manual")
    print("웹 브라우저를 디밍 조기에 조기실 완료")
    print("Connected to server")
    
    # 백그라운드 이벤트 루프 시작
    loop_thread = threading.Thread(target=start_event_loop, daemon=True)
    loop_thread.start()
    logger.info("백그라운드 이벤트 루프 시작")
    
    print("Interaction updated: " + datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3])
    
    try:
        socketio.run(app, host='0.0.0.0', 
                    port=5000, 
                    debug=False,
                    allow_unsafe_werkzeug=True,
                    log_output=False)
    except KeyboardInterrupt:
        print("\n서버를 종료합니다...")
    except Exception as e:
        print(f"서버 실행 중 오류 발생: {e}")
    finally:
        # 정리 작업
        if HARDWARE_AVAILABLE and ble_controller:
            try:
                run_async_in_loop(cleanup_hardware())
                logger.info("하드웨어 정리 완료")
            except:
                pass
        
        # 이벤트 루프 정리
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
        
        print("서버 종료 완료")
