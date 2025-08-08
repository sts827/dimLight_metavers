#!/bin/bash
# SD카드 이전 후 자동 환경설정 스크립트
# /home/allione/Desktop/SM_allione/scripts/auto_setup.sh
set -e

LOG_FILE="/home/allione/Desktop/auto_setup.log"
SETUP_FLAG="/home/allione/Desktop/.auto_setup_completed"
APP_DIR="/home/allione/Desktop/SM_allione"

# 로그 함수
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 이미 설정이 완료되었는지 확인
if [ -f "$SETUP_FLAG" ]; then
    log "자동 설정이 이미 완료됨. 종료."
    exit 0
fi

log "=== 라즈베리파이 Zero 2W 자동 환경설정 시작 ==="

# 0. allione 사용자 생성 및 설정
log "allione 사용자 설정 확인 중..."
if ! id "allione" &>/dev/null; then
    log "allione 사용자 생성 중..."
    sudo useradd -m -s /bin/bash allione
    echo "allione:allione1543" | sudo chpasswd
    sudo usermod -aG sudo,gpio,i2c,spi,audio,video allione
    log "allione 사용자 생성 완료"
else
    log "allione 사용자가 이미 존재함"
fi

# Desktop 디렉토리 생성
if [ ! -d "/home/allione/Desktop" ]; then
    sudo mkdir -p /home/allione/Desktop
    sudo chown allione:allione /home/allione/Desktop
    log "Desktop 디렉토리 생성 완료"
fi

# 1. 환경별 로그 기록 시작
log "환경별 상세 로그 기록 중..."
if [ -f "$APP_DIR/scripts/environment_logger.sh" ]; then
    chmod +x "$APP_DIR/scripts/environment_logger.sh"
    "$APP_DIR/scripts/environment_logger.sh"
    log "환경별 로그 기록 완료: /home/allione/Desktop/SM_allione/test/migration_logs/latest"
else
    log "환경 로깅 스크립트를 찾을 수 없음"
fi

# 1. 하드웨어 모델 감지
MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
log "감지된 모델: $MODEL"

# Zero 2W 확인
if [[ "$MODEL" == *"Zero 2"* ]]; then
    log "라즈베리파이 Zero 2W 감지됨"
    IS_ZERO2W=true
else
    log "다른 라즈베리파이 모델 ($MODEL)"
    IS_ZERO2W=false
fi

# 2. 메모리 정보 확인
TOTAL_MEM=$(free -m | awk 'NR==2{print $2}')
log "사용 가능한 메모리: ${TOTAL_MEM}MB"

# 3. Zero 2W용 최적화 설정
if [ "$IS_ZERO2W" = true ] || [ "$TOTAL_MEM" -lt 1000 ]; then
    log "저사양 환경 감지 - 최적화 설정 적용"
    
    # 3.1. systemd 서비스 파일 설치
    SOURCE_SERVICE="${APP_DIR}/scripts/SM_allione.service"
    TARGET_SERVICE="/etc/systemd/system/SM_allione.service"
    
    if [ -f "$SOURCE_SERVICE" ]; then
        log "systemd 서비스 파일 설치 중..."
        sudo cp "$SOURCE_SERVICE" "$TARGET_SERVICE"
        sudo systemctl daemon-reload
        sudo systemctl enable SM_allione.service
        log "systemd 서비스 설치 완료 (이미 Zero 2W 최적화됨)"
    else
        log "경고: 서비스 파일을 찾을 수 없습니다: $SOURCE_SERVICE"
    fi
    
    # 3.2. 스왑 파일 설정 (Zero 2W의 경우 중요)
    log "스왑 파일 설정 중..."
    sudo dphys-swapfile swapoff 2>/dev/null || true
    sudo sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=512/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
    log "스왑 파일 설정 완료 (512MB)"
    
    # 3.3. GPU 메모리 최소화
    log "GPU 메모리 최적화 중..."
    BOOT_CONFIG="/boot/firmware/config.txt"
    [ ! -f "$BOOT_CONFIG" ] && BOOT_CONFIG="/boot/config.txt"
    
    if ! grep -q "gpu_mem=16" "$BOOT_CONFIG"; then
        echo "gpu_mem=16" | sudo tee -a "$BOOT_CONFIG"
        log "GPU 메모리를 16MB로 설정"
    fi
    
    # 3.4. 불필요한 서비스 비활성화
    log "불필요한 서비스 비활성화 중..."
    services_to_disable=(
        "avahi-daemon"
        "triggerhappy"
        "bluealsa"
        "hciuart"
    )
    
    for service in "${services_to_disable[@]}"; do
        if systemctl is-enabled "$service" >/dev/null 2>&1; then
            sudo systemctl disable "$service"
            sudo systemctl stop "$service" 2>/dev/null || true
            log "$service 서비스 비활성화"
        fi
    done
fi

# 4. 네트워크 자동 설정
log "네트워크 자동 설정 중..."

# 4.1. SSH 최적화 및 활성화
log "SSH 서비스 최적화 중..."
if ! systemctl is-enabled ssh >/dev/null 2>&1; then
    sudo systemctl enable ssh
    sudo systemctl start ssh
    log "SSH 서비스 활성화"
fi

# SSH 최적화 적용 (Zero 2W 전용)
if [ "$IS_ZERO2W" = true ] || [ "$TOTAL_MEM" -lt 1000 ]; then
    log "Zero 2W SSH 최적화 적용 중..."
    
    # SSH 서버 설정 최적화
    if [ ! -f "/etc/ssh/sshd_config.backup" ]; then
        sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
        log "SSH 설정 백업 완료"
    fi
    
    # Zero 2W 최적화 설정 추가
    sudo tee -a /etc/ssh/sshd_config << 'EOF'

# Zero 2W SSH 최적화 설정
UseDNS no
GSSAPIAuthentication no
GSSAPICleanupCredentials no
LoginGraceTime 30
MaxSessions 3
MaxStartups 3:30:5
Ciphers aes128-ctr,aes256-ctr
MACs hmac-sha2-256,hmac-sha2-512
TCPKeepAlive yes
ClientAliveInterval 30
ClientAliveCountMax 3
MaxAuthTries 3
Compression yes
AllowUsers allione pi
EOF
    
    # 네트워크 최적화
    sudo tee /etc/sysctl.d/99-zero2w-ssh.conf << 'EOF'
# Zero 2W SSH 네트워크 최적화
net.core.rmem_default = 262144
net.core.rmem_max = 524288
net.core.wmem_default = 262144
net.core.wmem_max = 524288
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_fastopen = 1
EOF
    
    sudo sysctl -p /etc/sysctl.d/99-zero2w-ssh.conf >/dev/null 2>&1 || true
    
    # SSH 서비스 재시작
    sudo systemctl restart ssh
    log "SSH 최적화 완료"
fi

# 4.2. Wi-Fi 설정 확인 및 백업된 설정 복원 (NetworkManager 방식)
if [ -f "/home/allione/wifi_backup.conf" ]; then
    log "백업된 Wi-Fi 설정 복원 중... (NetworkManager 호환)"
    # NetworkManager는 자동으로 연결 설정을 관리하므로 별도 복원 불필요
    # 필요시 nmcli를 통해 연결 추가
    log "NetworkManager가 자동으로 Wi-Fi 설정 관리"
fi

# 4.3. 여러 Wi-Fi 네트워크 자동 설정 (NetworkManager 방식)
log "All-I-ONE_5G 포함 다중 Wi-Fi 네트워크 설정 추가 중..."

# NetworkManager를 통한 Wi-Fi 연결 추가 (실제 네트워크 이름 반영)
wifi_networks=(
    "All-I-ONE:allione1543"
    "All-I-ONE (TEMP):allione1543"
    "All-I-ONE_5G:allione1543"
    "Emergency_Hotspot:raspberry2w"
)

for network in "${wifi_networks[@]}"; do
    ssid="${network%%:*}"
    password="${network##*:}"
    
    # 이미 존재하는 연결인지 확인
    if ! nmcli connection show "$ssid" >/dev/null 2>&1; then
        log "Wi-Fi 네트워크 추가: $ssid"
        nmcli device wifi connect "$ssid" password "$password" 2>/dev/null || {
            # 직접 연결이 안되면 연결 프로필만 생성
            nmcli connection add type wifi con-name "$ssid" ssid "$ssid" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$password" 2>/dev/null || true
        }
    else
        log "Wi-Fi 네트워크 이미 존재: $ssid"
    fi
done

# 개방형 네트워크들 추가
open_networks=("iptime" "KT_WiFi" "U+Net")
for ssid in "${open_networks[@]}"; do
    if ! nmcli connection show "$ssid" >/dev/null 2>&1; then
        log "개방형 Wi-Fi 네트워크 추가: $ssid"
        nmcli connection add type wifi con-name "$ssid" ssid "$ssid" wifi-sec.key-mgmt none 2>/dev/null || true
    fi
done

log "NetworkManager Wi-Fi 설정 완료"

# 5. 애플리케이션 설정 최적화
log "애플리케이션 설정 최적화 중..."

APP_DIR="/home/allione/Desktop/SM_allione"
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    
    # 5.1. Python 가상환경 재구성 (아키텍처 차이 대응)
    if [ -d "venv" ]; then
        log "Python 가상환경 재구성 중..."
        rm -rf venv
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        log "Python 가상환경 재구성 완료"
    fi
    
    # 5.2. 로그 파일 정리
    log "로그 파일 정리 중..."
    > app.log  # 기존 로그 초기화
    
    # 5.3. 권한 재설정
    sudo chown -R allione:allione "$APP_DIR"
    log "파일 권한 재설정 완료"
fi

# 6. 부팅 최적화
log "부팅 최적화 설정 중..."

# 6.1. 부팅 시 자동 시작할 서비스만 남기기
if [ "$IS_ZERO2W" = true ]; then
    # Zero 2W는 부팅 시간이 중요하므로 불필요한 서비스 지연 시작
    sudo systemctl disable systemd-networkd-wait-online.service
    log "네트워크 대기 서비스 비활성화"
fi

# 7. 네트워크 연결 상태 확인 및 IP 알림
log "네트워크 연결 상태 확인 중... (All-I-ONE_5G 우선 연결 시도)"
for i in {1..30}; do
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        IP_ADDRESS=$(hostname -I | awk '{print $1}')
        CONNECTED_SSID=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2 2>/dev/null || echo "확인 불가")
        log "네트워크 연결 성공! IP 주소: $IP_ADDRESS"
        log "연결된 Wi-Fi: $CONNECTED_SSID"
        
        # IP 주소를 파일로 저장 (SSH 접속용)
        echo "$IP_ADDRESS" > /home/allione/current_ip.txt
        echo "$CONNECTED_SSID" > /home/allione/current_wifi.txt
        log "IP 주소가 /home/allione/current_ip.txt에 저장됨"
        log "Wi-Fi 정보가 /home/allione/current_wifi.txt에 저장됨"
        break
    fi
    log "네트워크 연결 대기 중... ($i/30)"
    sleep 2
done

# 8. 서비스 시작
log "SM_allione 서비스 시작 중..."
if systemctl is-active --quiet SM_allione; then
    sudo systemctl restart SM_allione
else
    sudo systemctl start SM_allione
fi

# 9. 설정 완료 표시
touch "$SETUP_FLAG"
log "자동 환경설정 완료!"

# 10. 상태 요약 출력
log "=== 설정 완료 요약 ==="
log "모델: $MODEL"
log "메모리: ${TOTAL_MEM}MB"
log "연결된 Wi-Fi: $(cat /home/allione/current_wifi.txt 2>/dev/null || echo '확인 불가')"
log "IP 주소: $(cat /home/allione/current_ip.txt 2>/dev/null || echo '확인 불가')"
log "웹 애플리케이션: http://$(cat /home/allione/current_ip.txt 2>/dev/null || echo 'IP'):5000"
log "SSH 접속: ssh allione@$(cat /home/allione/current_ip.txt 2>/dev/null || echo 'IP')"

# 11. 재부팅 알림 (설정 적용을 위해)
if [ "$IS_ZERO2W" = true ] && [ ! -f "/home/allione/.reboot_done" ]; then
    log "최적화 설정 적용을 위해 10초 후 재부팅됩니다..."
    touch /home/allione/.reboot_done
    sleep 10
    sudo reboot
fi

log "자동 환경설정 스크립트 실행 완료"