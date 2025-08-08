#!/usr/bin/env python3
"""
DALI 장치 설정 관리자
동적 장치 매핑 및 그룹 관리
"""

import json
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class DeviceConfigManager:
    """장치 설정 관리 클래스"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # 기본 설정 파일 경로
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(project_root, "config", "device_map.json")
        
        self.config_path = config_path
        self.config_data = {}
        self.last_loaded = None
        self.load_config()
    
    def load_config(self) -> bool:
        """설정 파일 로드"""
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"설정 파일을 찾을 수 없음: {self.config_path}")
                self._create_default_config()
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            
            self.last_loaded = datetime.now()
            logger.info(f"장치 설정 로드 완료: {self.config_path}")
            
            # 설정 검증
            if self._validate_config():
                return True
            else:
                logger.error("설정 파일 검증 실패")
                return False
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """설정 파일 유효성 검사"""
        required_keys = ['groups', 'devices', 'settings']
        
        for key in required_keys:
            if key not in self.config_data:
                logger.error(f"필수 키 누락: {key}")
                return False
        
        # 그룹과 장치 일관성 검사
        for group_id, group_info in self.config_data['groups'].items():
            for device_id in group_info.get('devices', []):
                if device_id not in self.config_data['devices']:
                    logger.warning(f"그룹 {group_id}에 정의되지 않은 장치: {device_id}")
        
        return True
    
    def _create_default_config(self):
        """기본 설정 파일 생성"""
        logger.info("기본 설정 파일 생성 중...")
        
        default_config = {
            "version": "1.0",
            "description": "DALI 조명 장치 매핑 설정 (기본값)",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "groups": {
                "G1": {
                    "name": "1그룹 조명",
                    "description": "기본 그룹",
                    "devices": ["DALLA1", "DALLA2", "DALLA3"]
                }
            },
            "devices": {
                "DALLA1": {
                    "mac": "E4:B3:23:A2:F6:F2",
                    "driver_id": 1,
                    "name": "A1 조명",
                    "group": "G1",
                    "status": "active"
                },
                "DALLA2": {
                    "mac": "E4:B3:23:A2:D1:EE",
                    "driver_id": 2,
                    "name": "A2 조명", 
                    "group": "G1",
                    "status": "active"
                },
                "DALLA3": {
                    "mac": "E4:B3:23:A2:D1:CE",
                    "driver_id": 3,
                    "name": "A3 조명",
                    "group": "G1", 
                    "status": "active"
                }
            },
            "settings": {
                "max_devices_per_group": 3,
                "supported_groups": ["G1"],
                "active_groups": ["G1"]
            }
        }
        
        # 디렉토리 생성
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            logger.info(f"기본 설정 파일 생성됨: {self.config_path}")
        except Exception as e:
            logger.error(f"기본 설정 파일 생성 실패: {e}")
    
    def get_device_map(self) -> Dict[str, Dict[str, Any]]:
        """BLE 컨트롤러용 장치 매핑 반환"""
        device_map = {}
        
        for device_id, device_info in self.config_data.get('devices', {}).items():
            device_map[device_id] = {
                "mac": device_info.get('mac', ''),
                "driver_id": device_info.get('driver_id', 0)
            }
        
        return device_map
    
    def get_group_devices(self, group_id: str) -> List[str]:
        """그룹의 장치 목록 반환"""
        group_info = self.config_data.get('groups', {}).get(group_id, {})
        return group_info.get('devices', [])
    
    def get_active_groups(self) -> List[str]:
        """활성화된 그룹 목록 반환"""
        return self.config_data.get('settings', {}).get('active_groups', ['G1'])
    
    def get_active_devices(self) -> List[str]:
        """활성 상태인 장치 목록 반환"""
        active_devices = []
        
        for device_id, device_info in self.config_data.get('devices', {}).items():
            if device_info.get('status') == 'active':
                active_devices.append(device_id)
        
        return active_devices
    
    def get_device_info(self, device_id: str) -> Optional[Dict[str, Any]]:
        """특정 장치 정보 반환"""
        return self.config_data.get('devices', {}).get(device_id)
    
    def get_group_info(self, group_id: str) -> Optional[Dict[str, Any]]:
        """특정 그룹 정보 반환"""
        return self.config_data.get('groups', {}).get(group_id)
    
    def add_device(self, device_id: str, device_info: Dict[str, Any]) -> bool:
        """새 장치 추가"""
        try:
            if device_id in self.config_data.get('devices', {}):
                logger.warning(f"장치 {device_id}가 이미 존재함")
                return False
            
            # 필수 필드 검증
            required_fields = ['mac', 'driver_id', 'name', 'group']
            for field in required_fields:
                if field not in device_info:
                    logger.error(f"필수 필드 누락: {field}")
                    return False
            
            # 기본값 설정
            device_info.setdefault('status', 'inactive')
            device_info.setdefault('location', '')
            device_info.setdefault('notes', '')
            
            self.config_data.setdefault('devices', {})[device_id] = device_info
            
            # 그룹에도 추가
            group_id = device_info['group']
            if group_id in self.config_data.get('groups', {}):
                group_devices = self.config_data['groups'][group_id].setdefault('devices', [])
                if device_id not in group_devices:
                    group_devices.append(device_id)
            
            return self.save_config()
            
        except Exception as e:
            logger.error(f"장치 추가 실패: {e}")
            return False
    
    def remove_device(self, device_id: str) -> bool:
        """장치 제거"""
        try:
            if device_id not in self.config_data.get('devices', {}):
                logger.warning(f"장치 {device_id}를 찾을 수 없음")
                return False
            
            device_info = self.config_data['devices'][device_id]
            group_id = device_info.get('group')
            
            # 장치 제거
            del self.config_data['devices'][device_id]
            
            # 그룹에서도 제거
            if group_id and group_id in self.config_data.get('groups', {}):
                group_devices = self.config_data['groups'][group_id].get('devices', [])
                if device_id in group_devices:
                    group_devices.remove(device_id)
            
            return self.save_config()
            
        except Exception as e:
            logger.error(f"장치 제거 실패: {e}")
            return False
    
    def update_device_status(self, device_id: str, status: str) -> bool:
        """장치 상태 업데이트"""
        try:
            if device_id not in self.config_data.get('devices', {}):
                logger.error(f"장치 {device_id}를 찾을 수 없음")
                return False
            
            valid_statuses = ['active', 'inactive', 'maintenance', 'error']
            if status not in valid_statuses:
                logger.error(f"잘못된 상태값: {status}")
                return False
            
            self.config_data['devices'][device_id]['status'] = status
            return self.save_config()
            
        except Exception as e:
            logger.error(f"장치 상태 업데이트 실패: {e}")
            return False
    
    def activate_group(self, group_id: str) -> bool:
        """그룹 활성화"""
        try:
            if group_id not in self.config_data.get('groups', {}):
                logger.error(f"그룹 {group_id}를 찾을 수 없음")
                return False
            
            active_groups = self.config_data.setdefault('settings', {}).setdefault('active_groups', [])
            if group_id not in active_groups:
                active_groups.append(group_id)
                
                # 그룹의 모든 장치를 활성화
                group_devices = self.get_group_devices(group_id)
                for device_id in group_devices:
                    if device_id in self.config_data.get('devices', {}):
                        # 임시 MAC이 아닌 실제 장치만 활성화
                        device_info = self.config_data['devices'][device_id]
                        if not device_info.get('mac', '').startswith('AA:BB:CC:DD:EE'):
                            device_info['status'] = 'active'
                
                return self.save_config()
            
            return True
            
        except Exception as e:
            logger.error(f"그룹 활성화 실패: {e}")
            return False
    
    def deactivate_group(self, group_id: str) -> bool:
        """그룹 비활성화"""
        try:
            active_groups = self.config_data.get('settings', {}).get('active_groups', [])
            if group_id in active_groups:
                active_groups.remove(group_id)
                
                # 그룹의 모든 장치를 비활성화
                group_devices = self.get_group_devices(group_id)
                for device_id in group_devices:
                    if device_id in self.config_data.get('devices', {}):
                        self.config_data['devices'][device_id]['status'] = 'inactive'
                
                return self.save_config()
            
            return True
            
        except Exception as e:
            logger.error(f"그룹 비활성화 실패: {e}")
            return False
    
    def save_config(self) -> bool:
        """설정 파일 저장"""
        try:
            # 백업 생성
            backup_path = self.config_path + '.bak'
            if os.path.exists(self.config_path):
                import shutil
                shutil.copy2(self.config_path, backup_path)
            
            # 업데이트 시간 설정
            self.config_data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"설정 파일 저장됨: {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"설정 파일 저장 실패: {e}")
            return False
    
    def reload_if_changed(self) -> bool:
        """파일이 변경된 경우 다시 로드"""
        try:
            if not os.path.exists(self.config_path):
                return False
            
            file_mtime = datetime.fromtimestamp(os.path.getmtime(self.config_path))
            if not self.last_loaded or file_mtime > self.last_loaded:
                logger.info("설정 파일 변경 감지 - 다시 로드")
                return self.load_config()
            
            return True
            
        except Exception as e:
            logger.error(f"설정 파일 변경 확인 실패: {e}")
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """시스템 설정 반환"""
        return self.config_data.get('settings', {})
    
    def is_zero2w_optimized(self) -> bool:
        """Zero 2W 최적화 설정 확인"""
        settings = self.get_settings()
        zero2w_settings = settings.get('zero2w_optimizations', {})
        return zero2w_settings.get('enabled', False)
    
    def get_command_interval(self) -> float:
        """명령 간격 반환 (초)"""
        settings = self.get_settings()
        zero2w_settings = settings.get('zero2w_optimizations', {})
        interval_ms = zero2w_settings.get('command_interval_ms', 100)
        return interval_ms / 1000.0
    
    def get_status_summary(self) -> Dict[str, Any]:
        """설정 상태 요약 반환"""
        total_devices = len(self.config_data.get('devices', {}))
        active_devices = len(self.get_active_devices())
        total_groups = len(self.config_data.get('groups', {}))
        active_groups = len(self.get_active_groups())
        
        return {
            'config_path': self.config_path,
            'last_loaded': self.last_loaded.isoformat() if self.last_loaded else None,
            'last_updated': self.config_data.get('last_updated'),
            'version': self.config_data.get('version'),
            'total_devices': total_devices,
            'active_devices': active_devices,
            'total_groups': total_groups,
            'active_groups': active_groups,
            'zero2w_optimized': self.is_zero2w_optimized()
        }


# 전역 인스턴스
_device_config_manager = None

def get_device_config() -> DeviceConfigManager:
    """전역 장치 설정 관리자 인스턴스 반환"""
    global _device_config_manager
    if _device_config_manager is None:
        _device_config_manager = DeviceConfigManager()
    return _device_config_manager

def reload_device_config():
    """전역 장치 설정 다시 로드"""
    global _device_config_manager
    if _device_config_manager:
        _device_config_manager.reload_if_changed()
