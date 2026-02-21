# AI Infra Hub

Windows 11 로컬 환경에서 Ollama + Open WebUI를 Docker Compose로 구동하는 프라이빗 AI 에이전트 인프라.
외부 API 없이 로컬 LLM 기반 Tool Calling 에이전트를 실행한다.

## 아키텍처

```
[Open WebUI :3000]
  ├── Tools (Python)
  │     ├── 수식 계산기
  │     └── 현재 시각 조회
  ├── MCP (로컬 컨테이너)
  │     ├── mcp-filesystem  → workspace/ 파일 읽기/쓰기
  │     └── mcp-fetch       → 외부 URL 콘텐츠 조회
  └── MCP (원격)
        └── Tavily Search   → 실시간 웹검색
              └── https://mcp.tavily.com/mcp/

[Ollama :11434 (내부망 전용)]
  └── qwen2.5:14b (또는 원하는 모델)
```

## 사전 요구사항

- Docker Desktop (GPU 지원 활성화 권장)
- NVIDIA GPU + 드라이버 (CPU 모드도 가능)
- Git

## 빠른 시작

### 1. 환경 준비

```bash
git clone <repo-url>
cd ai-infra-hub

# named volume 생성 (최초 1회)
docker volume create ollama-models
docker volume create open-webui-data

# 환경 변수 설정
copy .env.example .env
# .env에서 WEBUI_SECRET_KEY 값을 랜덤 문자열로 변경
```

### 2. 실행

```bash
# CPU 전용
docker compose up -d

# GPU + MCP 서버 포함 (권장)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.mcp.yml up -d
```

### 3. 접속

브라우저에서 http://127.0.0.1:3000 접속 → 관리자 계정 생성

### 4. 모델 다운로드

Open WebUI 접속 후 좌측 하단 모델 다운로드, 또는:

```bash
docker exec -it ollama ollama pull qwen2.5:14b
```

## Docker Compose 파일 구성

| 파일 | 역할 |
|------|------|
| `docker-compose.yml` | 기본 구성 (Ollama + Open WebUI, CPU 전용) |
| `docker-compose.gpu.yml` | GPU 오버라이드 (NVIDIA GPU 활성화) |
| `docker-compose.mcp.yml` | MCP 서버 오버라이드 (filesystem, fetch 컨테이너 추가) |

## MCP 서버

### 로컬 컨테이너 (자동 실행)

`docker-compose.mcp.yml` 포함 시 자동으로 기동됩니다.

| 서비스 | 엔드포인트 | 기능 |
|--------|-----------|------|
| mcp-filesystem | `http://mcp-filesystem:8000/mcp` | `workspace/` 디렉터리 파일 읽기/쓰기 |
| mcp-fetch | `http://mcp-fetch:8000/mcp` | 외부 URL HTML → 텍스트 변환 조회 |

### Tavily Search (원격 MCP, 수동 등록 필요)

Tavily는 자체 호스팅 Remote MCP를 제공하므로 Docker 컨테이너 없이 URL만 등록합니다.

**등록 방법:**

1. https://app.tavily.com/ 에서 API 키 발급 (월 1,000건 무료, 카드 불필요)
2. Open WebUI → Admin → 설정 → 외부 도구
3. `+` 버튼 → 타입: **MCP Streamable HTTP**
4. URL: `https://mcp.tavily.com/mcp/?tavilyApiKey=<발급받은_키>`
5. ID: `tavily` / 이름: `Tavily Search` 입력 후 저장

> API 키는 Open WebUI 내부 DB(Docker named volume)에만 저장됩니다. 코드/git에 커밋되지 않습니다.

## AI 어시스턴트 에이전트 설정

Open WebUI Workspace → 모델에서 **AI 어시스턴트** 에이전트를 생성하고 아래 도구를 활성화합니다.

| 도구 | 종류 | 활성화 방법 |
|------|------|------------|
| 수식 계산기 | Python 함수 | Workspace → 도구에서 등록 후 에이전트에 연결 |
| 현재 시각 조회 | Python 함수 | 동일 |
| MCP Filesystem | MCP | Admin → 외부 도구 등록 후 에이전트에 연결 |
| MCP Fetch | MCP | 동일 |
| Tavily Search | MCP (원격) | 위 Tavily 등록 절차 완료 후 에이전트에 연결 |

**시스템 프롬프트 예시:**
```
당신은 도구(Tool)을 활용할 수 있는 AI 어시스턴트 입니다.
사용자가 시간이나 날짜를 물으면 get_current_datetime 도구를 호출하세요.
수학 계산 요청에는 calculate 도구를 호출하세요.
한국어로 답변합니다.
```

## 유용한 명령어

```bash
# 전체 스택 상태 확인
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.mcp.yml ps

# MCP 서버만 재시작
docker compose -f docker-compose.yml -f docker-compose.mcp.yml restart mcp-filesystem mcp-fetch

# 로그 확인
docker logs open-webui --tail 50
docker logs mcp-filesystem --tail 20
docker logs mcp-fetch --tail 20

# 전체 중지 (데이터 보존)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.mcp.yml down
```

## workspace 디렉터리

`workspace/` 폴더는 mcp-filesystem이 에이전트에게 노출하는 공유 디렉터리입니다.
에이전트가 파일을 읽고 쓸 수 있으며, 호스트에서도 직접 접근 가능합니다.

```
workspace/
└── .gitkeep   # 디렉터리 추적용 (내용물은 git 제외)
```

## 환경 변수 (.env)

| 변수 | 설명 |
|------|------|
| `WEBUI_SECRET_KEY` | Open WebUI JWT 서명 키 (반드시 변경) |

Tavily API 키는 `.env`에 저장하지 않습니다. Open WebUI Admin에서 직접 관리합니다.
