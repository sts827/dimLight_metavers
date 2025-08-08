#!/bin/bash

# 키오스크 모드 종료 스크립트

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

echo -e "${BLUE}🛑 키오스크 모드 종료${NC}"

# 웹 서버 종료
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  웹 서버 종료 중... (PID: $PID)${NC}"
        kill "$PID" 2>/dev/null || true
        sleep 2
        
        # 강제 종료가 필요한 경우
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
fi

# Chromium/Firefox 키오스크 프로세스 종료
BROWSER_PIDS=$(pgrep -f "chromium.*localhost:5000\|firefox.*localhost:5000" 2>/dev/null || true)
if [ ! -z "$BROWSER_PIDS" ]; then
    echo -e "${YELLOW}⚠️  키오스크 브라우저 종료 중...${NC}"
    for pid in $BROWSER_PIDS; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 2
    
    # 강제 종료
    BROWSER_PIDS=$(pgrep -f "chromium.*localhost:5000\|firefox.*localhost:5000" 2>/dev/null || true)
    if [ ! -z "$BROWSER_PIDS" ]; then
        for pid in $BROWSER_PIDS; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
fi

# 임시 브라우저 데이터 정리
if [ -d "/tmp/kiosk-browser" ]; then
    echo -e "${BLUE}🧹 임시 브라우저 데이터 정리 중...${NC}"
    rm -rf /tmp/kiosk-browser 2>/dev/null || true
fi

# 포트 5000 확인
PORT_PROCESS=$(lsof -t -i:5000 2>/dev/null || true)
if [ ! -z "$PORT_PROCESS" ]; then
    echo -e "${YELLOW}⚠️  포트 5000을 사용하는 프로세스가 남아있습니다${NC}"
    for pid in $PORT_PROCESS; do
        kill "$pid" 2>/dev/null || true
    done
fi

echo -e "${GREEN}✅ 키오스크 모드가 완전히 종료되었습니다${NC}"
echo -e "${BLUE}💡 다시 시작하려면: ./kiosk.sh${NC}" 