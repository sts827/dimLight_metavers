from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import time
from domain.models import Schedule, WeekDay
from app.usecases.schedule_change import ChangeScheduleUseCase, ChangeScheduleRequest
from app.services import SystemStateService
from app.gateways import ScheduleRepository


@dataclass
class ScheduleViewState:
    """스케줄 설정 화면 상태"""
    schedules: List[Schedule]
    selected_schedule_id: Optional[str] = None
    is_enabled: bool = False
    selected_weekdays: List[WeekDay] = None
    on_time: time = time(9, 0)  # 기본값 09:00
    off_time: time = time(18, 0)  # 기본값 18:00
    is_time_picker_visible: bool = False
    time_picker_type: str = ""  # "on_time" or "off_time"
    error_message: Optional[str] = None
    success_message: Optional[str] = None
    
    def __post_init__(self):
        if self.selected_weekdays is None:
            self.selected_weekdays = []


class ScheduleViewModel:
    """스케줄 설정 뷰모델"""
    
    def __init__(
        self,
        change_schedule_usecase: ChangeScheduleUseCase,
        schedule_repo: ScheduleRepository,
        system_state_service: SystemStateService
    ):
        self.change_schedule_usecase = change_schedule_usecase
        self.schedule_repo = schedule_repo
        self.system_state_service = system_state_service
        self._state = ScheduleViewState(schedules=[])
    
    def get_state(self) -> ScheduleViewState:
        """현재 상태 조회"""
        try:
            # 모든 스케줄 조회
            schedules = self.schedule_repo.get_all_schedules()
            self._state.schedules = schedules
            
            return self._state
            
        except Exception as e:
            self._state.error_message = f"스케줄 정보 조회 중 오류가 발생했습니다: {str(e)}"
            return self._state
    
    def select_schedule(self, schedule_id: str) -> None:
        """스케줄 선택"""
        self._state.selected_schedule_id = schedule_id
        self._state.error_message = None
        self._state.success_message = None
        
        # 선택된 스케줄 정보 로드
        for schedule in self._state.schedules:
            if schedule.id == schedule_id:
                self._state.is_enabled = schedule.is_enabled
                self._state.selected_weekdays = schedule.weekdays.copy()
                self._state.on_time = schedule.on_time
                self._state.off_time = schedule.off_time
                break
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def toggle_schedule_enabled(self, schedule_id: str) -> None:
        """스케줄 On/Off 토글"""
        try:
            response = self.change_schedule_usecase.toggle_schedule(schedule_id)
            
            if response.success:
                self._state.success_message = response.message
                self._state.error_message = None
                
                # 상태 업데이트
                if response.schedule:
                    self._state.is_enabled = response.schedule.is_enabled
                    
                    # 스케줄 목록 업데이트
                    for i, schedule in enumerate(self._state.schedules):
                        if schedule.id == schedule_id:
                            self._state.schedules[i] = response.schedule
                            break
            else:
                self._state.error_message = response.message
                self._state.success_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"스케줄 토글 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def toggle_weekday(self, weekday: WeekDay) -> None:
        """요일 선택/해제 토글"""
        if weekday in self._state.selected_weekdays:
            self._state.selected_weekdays.remove(weekday)
        else:
            self._state.selected_weekdays.append(weekday)
        
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def is_weekday_selected(self, weekday: WeekDay) -> bool:
        """요일 선택 여부 확인"""
        return weekday in self._state.selected_weekdays
    
    def adjust_time(self, time_type: str, minutes_delta: int) -> None:
        """시간 조정 (+/- 30분 단위)"""
        if not self._state.selected_schedule_id:
            self._state.error_message = "스케줄을 먼저 선택해주세요"
            return
        
        try:
            response = self.change_schedule_usecase.adjust_time(
                self._state.selected_schedule_id,
                time_type,
                minutes_delta
            )
            
            if response.success:
                if response.schedule:
                    if time_type == "on_time":
                        self._state.on_time = response.schedule.on_time
                    elif time_type == "off_time":
                        self._state.off_time = response.schedule.off_time
                    
                    # 스케줄 목록 업데이트
                    for i, schedule in enumerate(self._state.schedules):
                        if schedule.id == self._state.selected_schedule_id:
                            self._state.schedules[i] = response.schedule
                            break
                
                self._state.success_message = response.message
                self._state.error_message = None
            else:
                self._state.error_message = response.message
                self._state.success_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"시간 조정 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def show_time_picker(self, time_type: str) -> None:
        """시간 선택기 표시"""
        self._state.is_time_picker_visible = True
        self._state.time_picker_type = time_type
        # 상호작용 시간 업데이트
        self.system_state_service.update_last_interaction()
    
    def hide_time_picker(self) -> None:
        """시간 선택기 숨기기"""
        self._state.is_time_picker_visible = False
        self._state.time_picker_type = ""
    
    def set_time(self, time_type: str, hour: int, minute: int) -> None:
        """시간 직접 설정"""
        try:
            new_time = time(hour, minute)
            
            if time_type == "on_time":
                self._state.on_time = new_time
            elif time_type == "off_time":
                self._state.off_time = new_time
            
            self.hide_time_picker()
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except ValueError as e:
            self._state.error_message = "올바른 시간을 입력해주세요"
    
    def save_schedule(self) -> None:
        """스케줄 저장"""
        if not self._state.selected_schedule_id:
            self._state.error_message = "스케줄을 먼저 선택해주세요"
            return
        
        try:
            request = ChangeScheduleRequest(
                schedule_id=self._state.selected_schedule_id,
                name="스케줄",  # 기본 이름
                is_enabled=self._state.is_enabled,
                weekdays=self._state.selected_weekdays.copy(),
                on_time=self._state.on_time,
                off_time=self._state.off_time
            )
            
            response = self.change_schedule_usecase.execute(request)
            
            if response.success:
                self._state.success_message = response.message
                self._state.error_message = None
                
                # 스케줄 목록 업데이트
                if response.schedule:
                    for i, schedule in enumerate(self._state.schedules):
                        if schedule.id == self._state.selected_schedule_id:
                            self._state.schedules[i] = response.schedule
                            break
            else:
                self._state.error_message = response.message
                self._state.success_message = None
            
            # 상호작용 시간 업데이트
            self.system_state_service.update_last_interaction()
            
        except Exception as e:
            self._state.error_message = f"스케줄 저장 중 오류가 발생했습니다: {str(e)}"
            self._state.success_message = None
    
    def get_weekday_display_names(self) -> Dict[WeekDay, str]:
        """요일 표시명"""
        return {
            WeekDay.MONDAY: "월",
            WeekDay.TUESDAY: "화",
            WeekDay.WEDNESDAY: "수",
            WeekDay.THURSDAY: "목",
            WeekDay.FRIDAY: "금",
            WeekDay.SATURDAY: "토",
            WeekDay.SUNDAY: "일"
        }
    
    def get_time_display(self, time_obj: time) -> str:
        """시간 표시 문자열"""
        return time_obj.strftime("%H:%M")
    
    def can_save_schedule(self) -> bool:
        """스케줄 저장 가능 여부"""
        if not self._state.selected_schedule_id:
            return False
        
        # 활성화된 스케줄의 경우 요일이 선택되어야 함
        if self._state.is_enabled and not self._state.selected_weekdays:
            return False
        
        # On/Off 시간이 같으면 안됨
        if self._state.on_time == self._state.off_time:
            return False
        
        return True
    
    def clear_messages(self) -> None:
        """메시지 초기화"""
        self._state.error_message = None
        self._state.success_message = None
