from typing import Protocol, List, Optional
from dataclasses import dataclass
from datetime import time
from domain.models import Schedule, WeekDay
from domain.rules import ScheduleRules
from domain.exceptions import ScheduleTimeException, ScheduleWeekdayException


class ScheduleRepository(Protocol):
    """스케줄 저장소 인터페이스"""
    def save_schedule(self, schedule: Schedule) -> None:
        ...
    
    def get_schedule(self, schedule_id: str) -> Schedule:
        ...
    
    def get_all_schedules(self) -> List[Schedule]:
        ...
    
    def delete_schedule(self, schedule_id: str) -> None:
        ...


@dataclass
class ChangeScheduleRequest:
    """스케줄 변경 요청"""
    schedule_id: str
    name: str
    is_enabled: bool
    weekdays: List[WeekDay]
    on_time: time
    off_time: time
    macro_id: Optional[str] = None


@dataclass
class ChangeScheduleResponse:
    """스케줄 변경 응답"""
    success: bool
    message: str
    schedule: Optional[Schedule] = None


class ChangeScheduleUseCase:
    """스케줄 변경 유스케이스"""
    
    def __init__(self, schedule_repo: ScheduleRepository):
        self.schedule_repo = schedule_repo
    
    def execute(self, request: ChangeScheduleRequest) -> ChangeScheduleResponse:
        """스케줄 변경 실행"""
        try:
            # 스케줄 시간 검증
            ScheduleRules.validate_schedule_time(request.on_time, request.off_time)
            
            # 요일 설정 검증 (스케줄이 활성화된 경우에만)
            if request.is_enabled:
                ScheduleRules.validate_weekdays(request.weekdays)
            
            # 기존 스케줄 조회
            existing_schedule = self.schedule_repo.get_schedule(request.schedule_id)
            
            # 스케줄 업데이트
            updated_schedule = Schedule(
                id=existing_schedule.id,
                name=request.name,
                is_enabled=request.is_enabled,
                weekdays=request.weekdays.copy(),
                on_time=request.on_time,
                off_time=request.off_time,
                macro_id=request.macro_id
            )
            
            # 저장
            self.schedule_repo.save_schedule(updated_schedule)
            
            return ChangeScheduleResponse(
                success=True,
                message="스케줄이 성공적으로 변경되었습니다",
                schedule=updated_schedule
            )
            
        except (ScheduleTimeException, ScheduleWeekdayException) as e:
            return ChangeScheduleResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return ChangeScheduleResponse(
                success=False,
                message=f"스케줄 변경 중 오류가 발생했습니다: {str(e)}"
            )
    
    def toggle_schedule(self, schedule_id: str) -> ChangeScheduleResponse:
        """스케줄 On/Off 토글"""
        try:
            schedule = self.schedule_repo.get_schedule(schedule_id)
            
            # 스케줄 활성화 상태 토글
            schedule.is_enabled = not schedule.is_enabled
            
            # 활성화할 때는 요일 검증
            if schedule.is_enabled:
                ScheduleRules.validate_weekdays(schedule.weekdays)
            
            # 저장
            self.schedule_repo.save_schedule(schedule)
            
            status = "활성화" if schedule.is_enabled else "비활성화"
            return ChangeScheduleResponse(
                success=True,
                message=f"스케줄이 {status}되었습니다",
                schedule=schedule
            )
            
        except ScheduleWeekdayException as e:
            return ChangeScheduleResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return ChangeScheduleResponse(
                success=False,
                message=f"스케줄 토글 중 오류가 발생했습니다: {str(e)}"
            )
    
    def adjust_time(self, schedule_id: str, time_type: str, minutes_delta: int) -> ChangeScheduleResponse:
        """시간 조정 (30분 단위)"""
        try:
            schedule = self.schedule_repo.get_schedule(schedule_id)
            
            if time_type == "on_time":
                current_time = schedule.on_time
                new_minutes = (current_time.hour * 60 + current_time.minute + minutes_delta) % (24 * 60)
                schedule.on_time = time(new_minutes // 60, new_minutes % 60)
            elif time_type == "off_time":
                current_time = schedule.off_time
                new_minutes = (current_time.hour * 60 + current_time.minute + minutes_delta) % (24 * 60)
                schedule.off_time = time(new_minutes // 60, new_minutes % 60)
            else:
                raise ValueError("time_type은 'on_time' 또는 'off_time'이어야 합니다")
            
            # 시간 검증
            ScheduleRules.validate_schedule_time(schedule.on_time, schedule.off_time)
            
            # 저장
            self.schedule_repo.save_schedule(schedule)
            
            return ChangeScheduleResponse(
                success=True,
                message="시간이 성공적으로 조정되었습니다",
                schedule=schedule
            )
            
        except (ScheduleTimeException, ValueError) as e:
            return ChangeScheduleResponse(
                success=False,
                message=str(e)
            )
        except Exception as e:
            return ChangeScheduleResponse(
                success=False,
                message=f"시간 조정 중 오류가 발생했습니다: {str(e)}"
            )
