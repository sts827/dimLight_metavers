#!/bin/bash

# 스마트 스위치 디밍 애플리케이션 중지 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 프로젝트 디렉토리 설정
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$PROJECT_DIR/app.pid"
KIOSK_PID_FILE="$PROJECT_DIR/kiosk.pid"
UNCLUTTER_PID_FILE="$PROJECT_DIR/.unclutter.pid"

echo -e "${BLUE}🛑 Smart Switch Dimming 애플리케이션 중지${NC}"

# 우선 키오스크 브라우저 종료 (있다면)
if [ -f "$KIOSK_PID_FILE" ]; then
    KPID=$(cat "$KIOSK_PID_FILE")
    if kill -0 "$KPID" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  키오스크 브라우저 종료 중... (PID: $KPID)${NC}"
        kill "$KPID" 2>/dev/null || true
        sleep 2
        kill -9 "$KPID" 2>/dev/null || true
    fi
    rm -f "$KIOSK_PID_FILE"
fi

# unclutter 종료 및 커서 복원
if [ -f "$UNCLUTTER_PID_FILE" ]; then
    UPID=$(cat "$UNCLUTTER_PID_FILE")
    kill "$UPID" 2>/dev/null || true
    rm -f "$UNCLUTTER_PID_FILE"
fi
command -v xsetroot >/dev/null 2>&1 && xsetroot -cursor_name left_ptr 2>/dev/null || true

# PID 파일 확인
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  서버 프로세스 종료 중... (PID: $PID)${NC}"
        kill "$PID"
        
        # 프로세스가 완전히 종료될 때까지 대기
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        
        # 강제 종료가 필요한 경우
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${RED}⚠️  강제 종료 중...${NC}"
            kill -9 "$PID"
        fi
        
        echo -e "${GREEN}✅ 서버가 성공적으로 중지되었습니다${NC}"
    else
        echo -e "${YELLOW}⚠️  서버가 이미 중지되어 있습니다${NC}"
    fi
    rm -f "$PID_FILE"
else
    echo -e "${YELLOW}⚠️  PID 파일이 없습니다. 서버가 실행 중이지 않거나 다른 방법으로 시작되었습니다${NC}"
fi

# 추가적으로 포트 5000을 사용하는 프로세스 확인
FLASK_PROCESSES=$(lsof -t -i:5000 2>/dev/null || true)
if [ ! -z "$FLASK_PROCESSES" ]; then
    echo -e "${YELLOW}⚠️  포트 5000을 사용하는 다른 프로세스가 발견되었습니다${NC}"
    echo -e "${BLUE}🔍 프로세스 목록:${NC}"
    lsof -i:5000
    echo -e "${YELLOW}이 프로세스들도 종료하시겠습니까? (y/N)${NC}"
    read -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for pid in $FLASK_PROCESSES; do
            kill "$pid" 2>/dev/null || true
        done
        echo -e "${GREEN}✅ 모든 관련 프로세스가 종료되었습니다${NC}"
    fi
fi

echo -e "${GREEN}🎯 완료!${NC}" 