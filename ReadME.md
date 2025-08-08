## 스마트 스위치 디밍

라즈베리파이 기반 IoT 스마트 조명 제어 시스템

### 전체 시스템 아키텍처(요약)
```
┌───────────────────────────────────────────────────────────────┐
│  UI (Jinja2 템플릿 + Vanilla JS)                              │
│  - 하단 탭 소프트 전환(페치 + history.pushState)             │
│  - AUTO 모드: 그룹/개별/매크로 탭 비활성화 → landing_auto    │
│  - 페이지 스크립트: script[data-page-script] 재실행 보장      │
│  - 이벤트 중복 방지(nav-lock, stopImmediatePropagation)       │
└──────────────┬────────────────────────────────────────────────┘
               │ HTTP/WS
┌──────────────▼────────────────────────────────────────────────┐
│  Flask API + Socket.IO                                        │
│  - /api/brightness, /api/macros, /api/system/mode             │
│  - /api/ble/* (health/stats/config/command/group/simulation)   │
│  - 로그 회전: log/app.log                                      │
└──────────────┬────────────────────────────────────────────────┘
               │ 내부 호출
┌──────────────▼────────────────────────────────────────────────┐
│  BLE 계층 (presentation/hardware/ble_controller.py)           │
│  - 연결 풀/락, per-MAC 최소 간격, 전역 동시성 제한            │
│  - notify 기반 ACK 대기(Future) + 타임아웃/에러 처리           │
│  - 시뮬레이션 모드 지원(실장비 없이 테스트)                   │
└──────────────┬────────────────────────────────────────────────┘
               │ BLE (NUS RX/TX)
┌──────────────▼────────────────────────────────────────────────┐
│  BLE-DALI 어댑터(주변기기) ↔ DALI 드라이버                     │
└───────────────────────────────────────────────────────────────┘
```

### BLE 통신 흐름(UI ↔ Server ↔ BLE ↔ DALI)
1) UI에서 슬라이더/토글/매크로 실행 → API/Socket 이벤트 전송
2) 서버에서 그룹/개별로 분기 후 BLE 계층 호출
3) BLE는 장치 맵(device_config)을 통해 mac/driver_id 조회 → 연결 풀에서 클라이언트 확보
4) 패킷([0xA0, driver_id, 0x01, 0x01, brightness, checksum])을 NUS RX로 write
5) 주변기기의 NUS TX notify 수신 → (mac, driver_id) 키의 Future 해제(ACK)
6) 성공/실패/타임아웃을 서버에 반환 → UI는 즉시/지연 피드백 갱신

운영 파라미터(런타임 튜닝)
- max_concurrent_commands: 동시에 처리할 명령 수(Zero2W=2, 일반=4 기본)
- min_command_interval: 동일 MAC 연속 전송 최소 간격(초)
- ack_timeout: ACK 대기 시간(초)

디버깅/튜닝 API
- GET /api/ble/health?include_scan=true&scan_timeout=3
- GET /api/ble/stats
- PUT /api/ble/config { ack_timeout, max_concurrent_commands, min_command_interval }
- PUT /api/ble/simulation { enable: true|false }
- POST /api/ble/command { dali_id, brightness }
- POST /api/ble/group { group_id, brightness }

로그 위치
- 운영 로그: `log/app.log` (회전)
- 테스트 산출물: `test/log/` (성능 분석 등 비운영 로그)

### 모델별 키오스크 환경 세팅(simple_kiosk.sh)
- 모델 감지
  - `/proc/device-tree/model`을 읽어 `Raspberry Pi Zero 2W` 여부 판단.
  - 명령행 옵션으로 강제 지정 가능: `--browser midori|chromium`, `--force-browser`.

- 공통(모델 무관)
  - 세션 타입 감지 후 브라우저 Ozone/GL 플래그 부여:
    - Wayland: `--ozone-platform=wayland --enable-features=UseOzonePlatform --use-gl=egl`
    - X11: `--ozone-platform=x11 --use-gl=egl`
  - 중복 실행 방지: `kiosk.lock`(프로세스 PID 기록)로 재진입 차단.

- Raspberry Pi Zero 2W 전용
  - 해상도: 800x480 우선 설정(`xrandr`로 HDMI/DSI/DPI 출력 순차 시도). 감지 실패 시 800x480 시도.
  - 메모리: RAM/Swap 검사 후 부족 시 임시 `/swapfile` 100MB 생성·활성(fstab 등록 시도), 실행 전 메모리 정리.
  - GPU 메모리 점검: `vcgencmd get_mem gpu`(<64MB 경고).
  - 브라우저: `midori` 우선 자동 선택(없으면 chromium 대체). WebKit 경량 플래그와 800x480 윈도우 크기 적용.

- Raspberry Pi 4B 등 기타 모델
  - 해상도: 감지 실패 시 1920x1080 또는 1280x720로 시도.
  - 브라우저: `chromium` 우선 자동 선택(없으면 midori 대체). 최소 키오스크 플래그 + EGL 렌더링 사용.

- 스크립트 주요 함수/위치
  - 브라우저 선택: `detect_and_select_browser()`
  - 브라우저 플래그: `generate_midori_flags()`, `generate_chromium_flags()`
  - 실행: `launch_browser()`(Zero 2W 분기 및 사전 메모리 점검 포함)

트러블슈팅
- Zero 2W에서 성능 저하 시 midori 사용 권장(`./scripts/simple_kiosk.sh --browser midori`).
- 락으로 실행이 막히면: `rm kiosk.lock` 후 재실행.

### Zero 2W 배포 TODO(경량화 운영 플랜)
목표: 개발 환경(IDE/에디터/디버거 등) 없이 운영에 필요한 최소 파일만 배포하고, 메모리/CPU 사용량을 최소화한다.

1) 저장소/패키징 전략(GitHub 권장)
- 메인 브랜치: 전체 소스 관리(GitHub)
- 릴리즈 아티팩트: `zip/tar.gz` 패키지 생성(코드 + `scripts/` + `presentation/api/*` + 정적/템플릿 + `SM_allione.service`)
- 선택: GitHub Actions로 릴리즈 시 자동 빌드/업로드

2) 장치 초기 세팅(Zero 2W)
- 필수 패키지만 설치: `sudo apt update && sudo apt install -y python3-venv midori xserver-xorg xinit unclutter`
- 스왑 확장: 200MB 이상(또는 기존 스왑 확인)
- 권한: `sudo usermod -a -G gpio,bluetooth $USER` 후 재로그인
- 불필요 서비스 중지: `sudo systemctl disable --now triggerhappy avahi-daemon cups` 등(환경에 맞게 선택)

3) 배포(미니멀)
- 장치로 아티팩트 전송: `scp release.tar.gz pi@DEVICE:/opt/sm`
- 배포 디렉터리: `/opt/sm`(권장) 또는 `/home/<user>/SM_allione`
- 가상환경 생성: `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt --no-cache-dir`

4) 서비스 구성(systemd)
- `/etc/systemd/system/SM_allione.service` 배치 → `sudo systemctl daemon-reload`
- 부팅 자동 시작: `sudo systemctl enable --now SM_allione`
- 키오스크 자동 시작이 필요하면 별도 `SM_allione-kiosk.service` 추가(사용자 세션 DISPLAY=:0 가정)

5) 런타임 최적화(Zero 2W)
- 브라우저: `midori` 기본, 800x480 고정(`simple_kiosk.sh` 자동 적용)
- BLE 튜닝(API): `PUT /api/ble/config {"max_concurrent_commands":2, "ack_timeout":1.2, "min_command_interval":0.2}`
- 로그: `log/app.log` 회전만 유지, `test/log/` 주기 삭제
- journald 휘발성 옵션 고려: `/etc/systemd/journald.conf`에서 `Storage=volatile`(운영 정책에 따라)

6) 개발 도구/IDE 미설치 원칙
- Cursor/VSCode 등 IDE 서버·에이전트 설치 금지(메모리 절약)
- 운영 장치에는 “코드 + 서비스 파일 + 스크립트”만 존재
- 원격 변경은 릴리즈 교체 또는 `rsync` 동기화

7) 운영 점검 체크리스트
- 메모리 사용률: `free -m`, `htop`
- 블루투스 서비스: `systemctl is-active bluetooth`
- 앱 상태: `./scripts/status.sh`, `tail -f log/app.log`
- 키오스크: `./scripts/simple_kiosk.sh --browser midori`(수동 기동 시)

8) 롤백/업데이트
- 현재 디렉터리를 백업 후 새 릴리즈 압축 해제
- `systemctl restart SM_allione`로 무중단 재기동 시도(요청 저부하 시간 권장)

### 메모리/CPU 점유 관리(Zero 2W 스펙 한도 내 구성)
Zero 2W는 RAM 512MB(권장 GPU 64MB)로 여유가 크지 않습니다. 다음 가이드로 점유를 예측·관리합니다.

- 목표 예산(권장)
  - OS/데스크톱/서비스: 180~220MB
  - 웹앱(Flask/SocketIO + BLE): 70~140MB
  - 브라우저(midori, 800x480): 80~140MB
  - 여유/파일 캐시/버퍼: ≥60MB

- 실측 방법
  - 전체: `free -m && echo; htop`
  - 상위 프로세스: `ps -eo pid,comm,%cpu,%mem,rss,etime --sort=-%mem | head -30`
  - 특정 PID 총합: `pmap -x <PID> | tail -n 1`
  - cgroup 단위: `systemd-cgtop`

- Cursor/IDE 관련 주의
  - Zero 2W에는 IDE/에이전트(예: cursor-server, vscode-server) 설치 금지(메모리 급증).
  - 남아있으면 종료/비활성: `pkill -f 'cursor|code|vscode-server'`, `systemctl --user disable --now *code*`.

- 서비스 cgroup 제한 예시
  - `/etc/systemd/system/SM_allione.service.d/override.conf`
    ```ini
    [Service]
    MemoryMax=180M
    CPUQuota=80%
    TasksMax=128
    Nice=5
    IOSchedulingClass=idle
    OOMScoreAdjust=-250
    ```
  - 적용: `sudo systemctl daemon-reload && sudo systemctl restart SM_allione`

- 브라우저 경량화
  - midori 사용(기본). 해상도 800x480 고정(`simple_kiosk.sh`).
  - 확장/플러그인/커스텀 폰트 최소화.

- 스왑/저널 최적화
  ```bash
  # 스왑 200MB 이상 권장(이미 구성돼 있으면 생략)
  sudo fallocate -l 200M /swapfile && sudo chmod 600 /swapfile \
    && sudo mkswap /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab \
    && sudo swapon -a

  # journald 크기 제한(또는 휘발성)
  echo -e '[Journal]\nSystemMaxUse=50M\nStorage=auto' | sudo tee /etc/systemd/journald.conf.d/limit.conf
  sudo systemctl restart systemd-journald
  ```

- BLE 런타임 튜닝(Zero 2W)
  - 엔드포인트: `PUT /api/ble/config`
  - 권장 초기값: `{ "max_concurrent_commands": 2, "ack_timeout": 1.2, "min_command_interval": 0.2 }`

- 운영 체크리스트(빠른 점검)
  - `tail -f log/app.log` 오류/타임아웃 비율 확인
  - `GET /api/ble/stats` 성공률/평균 응답(ms) 확인(>95%·<1000ms 권장)
  - `free -m` 여유 메모리 ≥ 60MB 유지

### 참고 문서 / 공식 링크
- Chromium Ozone/Wayland/X11: https://wiki.archlinux.org/title/Chromium#Wayland
- Chromium 명령행 스위치 목록: https://peter.sh/experiments/chromium-command-line-switches/
- systemd 리소스 제어(MemoryMax/CPUQuota 등): https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html
- systemd.exec(서비스 유닛 리소스/우선순위): https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- journald 설정(SystemMaxUse, Storage): https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html
- xrandr(해상도 설정) 개요: https://wiki.archlinux.org/title/Xrandr
- Midori 브라우저(공식): https://astian.org/midori/
- 스왑 생성/활성화: mkswap(8) https://man7.org/linux/man-pages/man8/mkswap.8.html , swapon(8) https://man7.org/linux/man-pages/man8/swapon.8.html , fallocate(2) https://man7.org/linux/man-pages/man2/fallocate.2.html
- cgroup 모니터링(systemd-cgtop): https://www.freedesktop.org/software/systemd/man/latest/systemd-cgtop.html
- 프로세스 메모리 측정: ps(1) https://man7.org/linux/man-pages/man1/ps.1.html , pmap(1) https://man7.org/linux/man-pages/man1/pmap.1.html , smem https://www.selenic.com/smem/
- Raspberry Pi Zero 2 W 스펙: https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/

### 🏗️ 아키텍처
```
┌─────────────────┐
│   UI Layer      │ ← 사용자 화면 (웹 기반 키오스크)
├─────────────────┤
│ View-Model      │ ← 사용자 이벤트, 상태 관리  
│ Controller      │
├─────────────────┤
│ Service Layer   │ ← REST API, MQTT, DB, GPIO 래퍼
├─────────────────┤
│ Domain / Core   │ ← 비즈니스 로직, 데이터 모델
└─────────────────┘
```

### 🚀 빠른 시작

1. **개발 환경 설정**
```bash
# 저장소 클론
git clone <repository-url>
cd SM_allione

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

2. **키오스크 모드 실행** (라즈베리파이 LCD 패널용)
```bash
./scripts/simple_kiosk.sh
```

3. **개발 서버만 실행** (개발용)
```bash
./scripts/start.sh --dev
```

4. **웹 브라우저에서 접속**
```
http://localhost:5000
```

### 📦 라즈베리파이 배포

**Raspberry Pi Zero 2W (권장 - 최적화됨)**
```bash
# Zero 2W 전용 최적화 설정 (처음 설치 시)
chmod +x scripts/setup_zero2w.sh
./scripts/setup_zero2w.sh

# 키오스크 모드 실행
./scripts/simple_kiosk.sh
```

**기타 라즈베리파이 모델**
```bash
# 배포 스크립트 실행 권한 부여
chmod +x scripts/deploy.sh

# 일반 배포
./scripts/deploy.sh

# 키오스크 모드 포함 배포
./scripts/deploy.sh --kiosk
```

### 🔄 라즈베리파이 Zero 2W 이전

**완전 자동화 이전 (권장)**
```bash
# 한 번의 명령으로 모든 준비 완료
./scripts/prepare_zero2w_migration.sh
```

**수동 이전**
```bash
# 1. 현재 시스템 백업
./scripts/prepare_migration.sh

# 2. 자동 설정 시스템 설치
./scripts/install_auto_setup.sh

# 3. boot 파티션 설정
./scripts/create_boot_setup.sh
```

**이전 완료 후**
- SD카드를 Zero 2W에 삽입
- 첫 부팅 시 자동으로 환경설정 실행 (5분 소요)
- IP 주소: `cat /home/allione/current_ip.txt`
- 웹 접속: `http://[IP]:5000`

### 🎮 주요 기능

- **그룹 조명 제어**: 여러 조명을 그룹으로 관리
- **개별 조명 제어**: 각 조명의 세밀한 밝기 조정  
- **매크로 기능**: 자주 사용하는 설정을 저장 (최대 3개)
- **스케줄링**: 요일별 자동 켜기/끄기 설정
- **Auto/Manual 모드**: 자동화 vs 수동 제어
- **센서 모니터링**: 소비전력, 온도, 습도 실시간 표시
- **키오스크 모드**: 터치스크린 전용 인터페이스 (마우스 커서 자동 숨김/복원)

### 🛠️ 기술 스택

**Backend:**
- Python 3.9+
- Flask + Flask-SocketIO
- Clean Architecture (Domain-Driven Design)

**Frontend:**
- HTML5 + CSS3 + Vanilla JavaScript
- Socket.IO (실시간 통신)
- 반응형 웹 디자인

**Hardware:**
- Raspberry Pi (Zero 2W, 4, 4B 지원)
- GPIO (릴레이 제어)
- BLE-DALI (조명 통신)
- MQTT (IoT 통신)

**Deployment:**
- systemd 서비스
- Nginx (프록시)
- Chromium 키오스크 모드

### 📂 프로젝트 구조

```
SM_allione/
├── domain/          # 도메인 모델, 비즈니스 규칙, 예외
├── app/            # 애플리케이션 서비스, 유스케이스
├── infra/          # 인프라스트럭처 (센서, 릴레이, MQTT 등)
├── presentation/   # 프레젠테이션 레이어
│   ├── ui/        # 웹 UI (템플릿, 정적 파일)
│   └── api/       # REST API, WebSocket
├── core/          # 코어 설정
├── scripts/       # 실행 및 관리 스크립트
│   ├── simple_kiosk.sh    # 메인 키오스크 모드 (추천)
│   ├── start.sh           # 웹서버 시작
│   ├── stop.sh            # 웹서버 중지
│   ├── status.sh          # 상태 확인
│   ├── deploy.sh          # 라즈베리파이 배포
│   └── debug_display.sh   # 디스플레이 문제 진단
└── test/          # 테스트 코드
```

### 🔧 설정

시스템 설정은 환경 변수나 설정 파일을 통해 관리:

- `FLASK_ENV`: 실행 환경 (development/production)
- `MQTT_BROKER_HOST`: MQTT 브로커 주소
- `DEVICE_IP`: 장치 IP 주소

### 📱 화면 구성

# 화면설계
## 설정 화면(main_settings.png 이미지 참고)
1. 설정 페이지는 매크로 설정, 스케쥴 설정, 모드 전환 장치 정보 4개 선택창으로 구성

2. 매크로 설정 화면 페이지 : 현재 조명 설정값(그룹/개별 제어에서 설정하여 현재 사용하는 밝기)를 등록, 매크로 등록을 선택하고 저장을 클릭하여 현재 값을 저장함.
이미 등록된 매크로를 다시 선택하여 저장을 누를 경우, 선택된 매크로 설정값이 변경됨(마지막으로 저장한 값이 저장됨). 이미 등록된 매크로 변경시, "매크로이름(사용자지정)"설정을 변경하시겠습니까? 확인 창 제공. 변경 확인 창 하단 확인/취소, 변경 확인창 확인 클릭시, 변경되었습니다 표시함. 이름 변경 클릭시 5글자 제한, 유효성 검사, 키패드표출(PC환경이 아닌 IoT기기(라즈베리파이4 lcd화면)에서 표출되어지기 떄문에 해당 부분 확인 필요), 매크로는 최대 3개까지만 생성 가능.


3. 스케쥴 설정화면 페이지  : Click시 스케쥴 On/Off기능, 요일 설정, 선택한 요일에 effect효과(배경색과 텍스트 색상 변경), 시간 변경 +,-아이콘으로 30분 단위로 변경되며, 시간을 클릭시, 다이얼 로그(아이폰 ios 시간 설정 참고: 위아래로 다이얼 효과 )효과, 유효성 검사 필요(On/Off시간이 같을 경우, 요일 설정을 하루도 선택하지 않았을 경우 저장 불가능).


4. 모드전환 설정 화면: 자동모드와 수동 모드 두가지 옵션 제공, Auto 모드 선택시 오토모드 대기 화면 표출(조작 불가, 조작가능하게 하려면 화면을 길게 터치하거나, 잠금 화면 아이콘을 클릭하여 manual 화면으로 자동화면 이동), Manual 모드 선택시 전체 기능 사용 가능

5. 장치 정보 설정 화면: 장치 정보중 장치명, 버전, 시리얼 넘버, 제조사는 고정값(변경불가), IP 주소 설정만 클리갛여 변경 가능, 클릭시 숫자 키패드 표출, 유효성 검사 IP  주소 형식이 안맞을 경우 IP 주소를 다시 확인하라는 텍스트 표출


## 사용 화면(landing_auto.png,landing_manual.png 이미지 참고)
1. 대기화면(auto/manual)
(1)manual 대기화면 : 소비전력, 온도, 습도 , 시계정보 표출 대기화면
-> 화면 터치시 메인 화면(그룹제어) 화면으로 전환
-> 5분 이상 해당 화면이 조작감지가 안될시 대기 화면 표출
(2)Auto 대기화면: 설정>모드 전환에서 오토모드 선택시 표출되는 화면
-> 화면 터치시 설정 > 모드 전환 페이지로 돌아감(오토모드 조작 불가)




## 🖥️ 키오스크 모드 특징

### 마우스 커서 관리
- **자동 숨김**: 키오스크 시작 시 `unclutter`로 마우스 커서 자동 숨김
- **자동 복원**: 키오스크 종료 시 마우스 커서 자동 복원
- **터치 유지**: 터치 입력은 정상 작동 (커서만 숨김)

### 터치 인터페이스 최적화
- **CSS 최적화**: `cursor: none`, `touch-action: manipulation`
- **터치 캘리브레이션**: `scripts/touch_calibrate.sh`로 정밀 조정
- **전체화면 모드**: `--kiosk`, `--start-fullscreen` 플래그

### 시스템 통합
- **자동 시작**: Systemd 서비스 연동
- **프로세스 관리**: PID 기반 안전한 종료
- **환경 설정**: X11 DISPLAY 자동 구성

## 개발 환경 
1. 웹‑기반 Chromium 키오스크

2. 공통 시스템 구조
- UILayer   <- 사용자 화면
- View-Model / Controller  <- 사용자 이벤트, 상태 관리
- Service Layer <-REST API, MQTT, DB, GPIO래퍼
- Domain / Core  <-비즈니스 로직, 데이터 모델

@확장성 포인트 : UI Layer는 프레임 워크 교체시 영향 최소화, 장치 I/O는 Service Layer에서만 담당하도록 분리

@디펜던시 방향
1. Presentation -> app -> domain(단방향)
2. infra는 외부(의존성)에서 application / domain에 주입(의존성 역전)


## 🔧 Raspberry Pi Zero 2W 전용 최적화

### 자동 최적화 기능
- **시스템 감지**: Zero 2W 자동 인식 및 최적화 모드 활성화
- **해상도 조정**: 성능 향상을 위해 720p로 자동 제한
- **메모리 관리**: swap 자동 설정 (200MB) 및 GC 튜닝
- **Chromium 최적화**: GPU 비활성화, 메모리 사용량 최소화
- **권한 설정**: gpio, bluetooth 그룹 자동 추가

### 성능 최적화 설정
```bash
# GPU 메모리 설정 (/boot/config.txt)
gpu_mem=64

# swap 설정 권장
sudo fallocate -l 200M /swapfile
sudo chmod 600 /swapfile  
sudo mkswap /swapfile
sudo swapon /swapfile

# 사용자 권한
sudo usermod -a -G gpio,bluetooth,i2c $USER
```

### Zero 2W 성능 특성
- **RAM**: 512MB (swap 200MB 권장)
- **CPU**: 4-core ARM Cortex-A53 1GHz
- **권장 해상도**: 1280x720 이하
- **브라우저**: Chromium (GPU 가속 비활성화)
- **동시 연결**: BLE 장치 최대 3-5개 권장

### 문제해결
```bash
# 메모리 부족 시
sudo systemctl restart SM_allione

# Bluetooth 문제 시  
sudo systemctl restart bluetooth

# GPIO 권한 문제 시
sudo usermod -a -G gpio $USER
# 재로그인 필요

# 성능 모니터링
htop
vcgencmd measure_temp
vcgencmd get_mem gpu
```

---

@라즈베리파이 배포
단일 바이너리 패키징, systemd 서비스 파일은 /etc/systemd/system/SM_allione.serivce로 관리
