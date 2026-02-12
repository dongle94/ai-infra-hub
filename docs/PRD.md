# PRD: Local AI Infrastructure Hub

> **Product Requirements Document**
> 버전: 1.0.0 | 작성일: 2026-02-12 | 상태: Draft

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [기술 스택](#3-기술-스택)
4. [단계별 실행 계획](#4-단계별-실행-계획)
5. [환경 요구사항](#5-환경-요구사항)
6. [보안 고려사항](#6-보안-고려사항)
7. [리스크 및 대응 방안](#7-리스크-및-대응-방안)
8. [향후 확장 방향](#8-향후-확장-방향)
9. [버전 관리 정책](#9-버전-관리-정책)

---

## 1. 프로젝트 개요

### 1.1 목적

Windows 11 로컬 환경에서 Ollama와 Open WebUI를 Docker Compose로 구동하여, 인터넷 연결 없이 동작하는 완전한 프라이빗 AI 에이전트 인프라를 구축한다.

외부 AI 서비스(OpenAI, Anthropic 등)에 대한 의존도를 줄이고, 민감한 데이터가 외부로 유출되지 않는 로컬 LLM 기반 워크플로우를 실현하는 것이 핵심 목적이다.

### 1.2 목표

| 목표 구분 | 내용 |
|---|---|
| 기능 목표 | Tool Calling이 가능한 로컬 AI 에이전트 구동 |
| 품질 목표 | GPU 환경에서 7B 모델 기준 10 tok/s 이상 응답 속도 |
| 보안 목표 | 모든 LLM 추론이 로컬에서만 수행, 외부 전송 없음 |
| 확장 목표 | MCP 서버 연동, RAG, 멀티에이전트로 단계적 확장 가능한 구조 |

### 1.3 범위

**In-Scope (이번 프로젝트 범위)**

- Docker Compose 기반 Ollama + Open WebUI 구동 환경 구축
- 오픈소스 LLM 모델(Qwen 2.5 계열) 로컬 서빙
- Open WebUI Tool 등록을 통한 Function Calling 에이전트 구현
- MCP 서버 연동 (filesystem, fetch, brave-search 등)
- 내장 ChromaDB 기반 RAG 구성

**Out-of-Scope (이번 프로젝트 범위 외)**

- 프로덕션 서버 배포 (클라우드 이전)
- 다중 사용자 접근 제어 (RBAC)
- 모델 파인튜닝 (LoRA, Full Fine-tuning)
- 모바일 클라이언트

---

## 2. 시스템 아키텍처

### 2.1 전체 구성도

```
[Windows 11 Host]
  |
  +-- Docker Desktop (WSL2 Backend)
        |
        +-- [ai-infra Network (bridge)]
              |
              +-- [open-webui container]  <-- 127.0.0.1:3000 (호스트 노출)
              |     - ghcr.io/open-webui/open-webui:main
              |     - Built-in ChromaDB (RAG)
              |     - Built-in Tool Registry
              |
              +-- [ollama container]      <-- 호스트 미노출 (내부 전용)
              |     - ollama/ollama:latest
              |     - GPU passthrough (Phase 2+)
              |     - Named Volume: ollama-models
              |
              +-- [mcp-* containers]      <-- Phase 4+
                    - filesystem, fetch, brave-search 등
                    - supergateway (stdio → SSE 변환)


[사용자 접근]
  브라우저 → http://127.0.0.1:3000 → Open WebUI

[데이터 흐름]
  사용자 입력
    → Open WebUI (메시지 처리)
      → Ollama API (http://ollama:11434)
        → LLM 모델 (추론)
          → Tool 호출 (필요 시)
            → 결과 반환
              → 스트리밍 응답
```

### 2.2 컴포넌트 역할 및 관계

```
+------------------+         +------------------+         +------------------+
|   Open WebUI     |         |     Ollama        |         |   LLM Models     |
|                  |  HTTP   |                  |  Local  |                  |
| - 채팅 인터페이스  +-------->+ /api/chat         +-------->+ qwen2.5:7b       |
| - Tool 등록/관리  |         | /api/generate     |         | qwen2.5:14b      |
| - Agent 설정     |         | /v1/chat/..       |         | (기타 모델)       |
| - RAG 관리       |         | /api/embeddings   |         |                  |
| - 사용자 인증     |         |                  |         |                  |
+------------------+         +------------------+         +------------------+
        |                                                          |
        | (Phase 3+)                                               | Named Volume
        v                                                          v
+------------------+                                    +------------------+
|   Tools / MCP    |                                    |  ollama-models   |
|                  |                                    |  (Docker Volume) |
| - 시간/날짜       |                                    |  ~4-20GB/model   |
| - 파일시스템      |                                    +------------------+
| - 웹 검색        |
| - HTTP fetch     |
+------------------+
```

### 2.3 네트워크 및 포트 구성

| 서비스 | 컨테이너 내부 포트 | 호스트 바인딩 | 접근 범위 |
|---|---|---|---|
| Open WebUI | 8080 | 127.0.0.1:3000 | 로컬 호스트만 |
| Ollama API | 11434 | 미노출 (내부 전용) | Docker 내부 네트워크만 |
| MCP 서버 (Phase 4+) | 8000 | 미노출 (내부 전용) | Docker 내부 네트워크만 |

> 보안 원칙: Ollama API는 절대 호스트에 직접 노출하지 않는다. Open WebUI를 통해서만 간접 접근한다.

### 2.4 데이터 영속성 구조

```
Docker Named Volumes (WSL2 기반, I/O 성능 최적화)
  |
  +-- ollama-models    : LLM 모델 파일 (GGUF 등), 4-20GB/모델
  |
  +-- open-webui-data  : 사용자 데이터, 대화 기록, ChromaDB 인덱스
                         Tool 설정, Agent 설정, 업로드 문서
```

---

## 3. 기술 스택

### 3.1 핵심 컴포넌트

| 컴포넌트 | 이미지/버전 | 역할 | 선정 이유 |
|---|---|---|---|
| Ollama | `ollama/ollama:latest` | LLM 로컬 서빙 엔진 | Windows/Mac/Linux 통합 지원, OpenAI 호환 API, GPU 추상화 |
| Open WebUI | `ghcr.io/open-webui/open-webui:main` | 웹 인터페이스 + 에이전트 플랫폼 | Tool 등록, RAG, 멀티모달 지원, 활발한 커뮤니티 |
| Docker Desktop | v4.24+ | 컨테이너 런타임 | WSL2 통합, GPU passthrough 지원 |
| WSL2 | Ubuntu (기본) | Docker 실행 계층 | Windows에서 Linux 컨테이너 구동 필수 |

### 3.2 LLM 모델 선정 기준

**MVP 권장 모델: `qwen2.5:7b`**

선정 이유:
- 한국어 처리 품질이 동급 모델 중 최상위 수준
- Tool Calling (Function Calling) 네이티브 지원
- 7B 파라미터로 8GB VRAM에서 구동 가능
- Q4_K_M 양자화로 VRAM 효율과 품질의 최적 균형

| VRAM 규모 | 권장 모델 | 예상 속도 (GPU) | 비고 |
|---|---|---|---|
| CPU-only | qwen2.5:7b (Q4_K_M) | 3-8 tok/s | 검증 목적으로 충분 |
| 8GB | qwen2.5:7b | 20-40 tok/s | MVP 운영 적합 |
| 12GB | qwen2.5:14b | 15-25 tok/s | 고품질 응답 |
| 24GB | qwen2.5:32b | 10-20 tok/s | 프로 수준 성능 |

**Tool Calling 지원 모델 대안**

| 모델 | 특징 | 적합 상황 |
|---|---|---|
| `llama3.1:8b` | Meta 공식, 영어 최강 | 영어 중심 작업 |
| `mistral-nemo:12b` | Mistral + NVIDIA 협업 | 균형잡힌 범용 |
| `command-r:35b` | Cohere, RAG 특화 | 문서 기반 Q&A |
| `qwen2.5-coder:7b` | 코드 생성 특화 | 개발 지원 에이전트 |

### 3.3 Open WebUI Tool & Function Calling

| 방식 | 설명 | 안정성 | 권장 여부 |
|---|---|---|---|
| Default 모드 | 시스템 프롬프트 주입 방식 | 낮음 (모델 의존적) | 비권장 |
| Native 모드 | Ollama API tools 파라미터 활용 | 높음 | 권장 |

**Tool 등록 방식:** Python 클래스(`class Tools`) 작성, docstring이 description으로 자동 사용됨

```python
class Tools:
    def get_current_time(self) -> str:
        """현재 시각을 반환합니다. Returns the current date and time."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

---

## 4. 단계별 실행 계획

### Phase 1: MVP - CPU-only 기본 동작 검증

**목표:** Docker Compose로 Ollama + Open WebUI를 실행하고, LLM과 대화할 수 있는 최소 환경 구축

**왜 CPU-only로 시작하는가?**
GPU 설정 없이 기본 동작을 먼저 검증함으로써 GPU 드라이버 이슈와 애플리케이션 이슈를 분리한다. 트러블슈팅 복잡도를 최소화하는 것이 핵심이다.

#### 구성 요소

- Ollama (CPU 모드)
- Open WebUI
- `qwen2.5:7b` 모델 (Q4_K_M 양자화)

#### 수행 작업

- [ ] WSL2 활성화 및 Docker Desktop 설치 확인
- [ ] `.wslconfig` 설정 (메모리 16GB+, 프로세서 8+, swap 16GB+)
- [ ] `docker-compose.yml` 작성 (CPU-only 설정)
- [ ] `WEBUI_SECRET_KEY` 환경 변수 설정
- [ ] `docker compose up -d` 실행
- [ ] Open WebUI 접속 (http://127.0.0.1:3000) 및 관리자 계정 생성
- [ ] `docker exec ollama ollama pull qwen2.5:7b` 모델 다운로드
- [ ] 기본 대화 테스트

#### docker-compose.yml 기본 구조

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - ai-infra
    restart: unless-stopped
    environment:
      - OLLAMA_KEEP_ALIVE=5m

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    ports:
      - "127.0.0.1:3000:8080"
    volumes:
      - open-webui-data:/app/backend/data
    networks:
      - ai-infra
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}
      - ENABLE_SIGNUP=true  # 초기 계정 생성 후 false로 변경
    depends_on:
      ollama:
        condition: service_started
    restart: unless-stopped

networks:
  ai-infra:
    driver: bridge

volumes:
  ollama-models:
    external: true  # 실수로 삭제 방지
  open-webui-data:
    external: true
```

#### 검증 방법

- [ ] `docker compose ps` 에서 두 컨테이너 모두 `running` 상태 확인
- [ ] Open WebUI 접속 화면 정상 로드 확인
- [ ] 모델 선택 후 "안녕하세요" 입력에 한국어 응답 확인
- [ ] `docker compose logs ollama` 에서 에러 없음 확인

#### 특히 주의할 점

- Named Volume을 `docker volume create` 로 먼저 생성해야 `external: true` 설정이 동작한다
- `WEBUI_SECRET_KEY`는 `.env` 파일에 관리하고, `.env`는 `.gitignore`에 추가한다
- `ENABLE_SIGNUP=true` 는 최초 관리자 계정 생성 직후 즉시 `false`로 변경한다
- 모델 다운로드는 수 GB이므로 안정적인 네트워크 환경에서 수행한다

---

### Phase 2: GPU 활성화 + 성능 최적화

**목표:** NVIDIA GPU를 Ollama에 연결하여 실용적인 응답 속도(10 tok/s 이상) 달성

**왜 별도 Phase로 분리하는가?**
GPU passthrough는 드라이버 버전, Docker Desktop 버전, WSL2 커널 버전의 삼각 의존성이 있다. Phase 1에서 애플리케이션 레이어가 정상 동작함을 확인한 후 GPU를 추가하면, 문제 발생 시 원인을 GPU 설정으로 명확히 한정할 수 있다.

#### 구성 요소

- NVIDIA 드라이버 v531.18 이상 (Windows 호스트)
- Docker Desktop v4.24 이상
- GPU 리소스 설정이 추가된 Ollama 컨테이너
- (VRAM에 따라) `qwen2.5:14b` 또는 `qwen2.5:32b`로 모델 업그레이드 고려

#### 수행 작업

- [ ] Windows 호스트에서 NVIDIA 드라이버 버전 확인 (`nvidia-smi`)
- [ ] Docker Desktop `Settings > Resources > Advanced > GPUs` 활성화 확인
- [ ] `docker-compose.yml` GPU 설정 추가
- [ ] `docker compose up -d --force-recreate ollama` 로 Ollama 재시작
- [ ] GPU 인식 확인

#### GPU 설정 추가 내용

```yaml
# ollama 서비스에 아래 항목 추가
services:
  ollama:
    # ... 기존 설정 유지 ...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

#### 검증 방법

- [ ] `docker exec ollama nvidia-smi` 에서 GPU 목록 확인
- [ ] `docker exec ollama ollama ps` 에서 모델이 GPU VRAM에 로드됨 확인
- [ ] 응답 생성 중 `nvidia-smi` 에서 GPU 사용률 상승 확인
- [ ] 10 tok/s 이상 응답 속도 체감 또는 측정

#### 특히 주의할 점

- WSL2 내부에 별도 CUDA Toolkit 설치 불필요. Windows 호스트 드라이버만으로 충분하다
- GPU가 없는 환경이라면 이 Phase는 건너뛰고 CPU-only로 계속 진행한다
- AMD GPU는 ROCm 설정이 별도로 필요하며, 이 문서의 범위 밖이다
- `OLLAMA_KEEP_ALIVE` 시간을 길게 설정하면 VRAM이 계속 점유되므로 개발 중에는 `5m` 수준으로 유지한다

---

### Phase 3: Tool 확장 (내장 Function Calling)

**목표:** Open WebUI의 Tool 등록 기능으로 실용적인 기능(시간/날짜, 간단한 계산, 파일 읽기 등)을 에이전트에 부여

**왜 MCP보다 내장 Tool을 먼저 구현하는가?**
Open WebUI의 내장 Tool 시스템은 Python 코드를 직접 등록하는 방식으로, MCP 서버 없이도 즉시 동작한다. MCP는 외부 서버 프로세스가 필요하므로 복잡도가 높다. 내장 Tool로 Function Calling의 동작 원리와 모델의 Tool 호출 품질을 먼저 검증하는 것이 효율적이다.

#### 구성 요소

- Open WebUI Tool Registry (내장)
- Python 기반 Tool 클래스 (직접 작성)
- Native Function Calling 모드 설정

#### 수행 작업

- [ ] Open WebUI 설정에서 Function Calling 모드를 "Native"로 변경
- [ ] 첫 번째 Tool: 현재 시각/날짜 반환 (`get_current_time`)
- [ ] 두 번째 Tool: 간단한 수식 계산 (`calculate`)
- [ ] Agent(커스텀 모델) 생성: Tool을 연결한 전용 어시스턴트 구성
- [ ] Tool Calling 동작 검증

#### Tool 개발 패턴

```python
class Tools:
    def get_current_datetime(self) -> str:
        """
        현재 날짜와 시각을 반환합니다.
        Returns the current date and time in ISO format.
        Use this when the user asks about the current time or date.
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S (KST)")

    def calculate(self, expression: str) -> str:
        """
        수학 표현식을 계산합니다.
        Evaluates a mathematical expression safely.
        :param expression: The mathematical expression to evaluate (e.g., "2 + 2 * 3")
        """
        try:
            # eval 대신 ast.literal_eval 또는 별도 파서 사용 권장
            result = eval(expression, {"__builtins__": {}}, {})
            return f"{expression} = {result}"
        except Exception as e:
            return f"계산 오류: {str(e)}"
```

#### 검증 방법

- [ ] "지금 몇 시야?" 질문에 Tool 호출 후 정확한 시각 응답 확인
- [ ] "3.14 * 5^2 계산해줘" 질문에 계산 Tool 호출 및 결과 확인
- [ ] Open WebUI 대화 화면에서 Tool 호출 과정(Thinking) 표시 확인
- [ ] Tool 없이 동일 질문 시 모델이 허구의 답변을 하지 않는지 비교

#### 특히 주의할 점

- Tool의 docstring이 LLM이 도구를 이해하는 핵심 정보다. 한국어와 영어를 병기하여 모델이 언제 이 Tool을 호출해야 하는지 명확히 기술한다
- `eval()` 사용은 보안 취약점이 된다. 계산기 Tool에는 반드시 안전한 수식 파서(`ast` 모듈 등)를 사용한다
- Native 모드는 모델이 Tool Calling을 지원해야만 동작한다. `qwen2.5:7b` 이상 사용을 권장한다
- Tool 실행 에러가 발생하면 LLM이 에러 메시지를 그대로 받아 혼란스러운 응답을 할 수 있으므로, 예외 처리를 철저히 한다

---

### Phase 4: MCP 서버 연동

**목표:** Model Context Protocol 서버를 Docker Compose에 추가하여, 파일시스템 접근, 웹 검색, HTTP fetch 등 강력한 외부 Tool을 에이전트에 연결

**왜 MCP인가?**
MCP는 Anthropic이 주도하는 표준 프로토콜로, 에이전트가 외부 시스템과 상호작용하는 방식을 표준화한다. 직접 Python Tool을 만드는 것보다 생태계의 기존 MCP 서버를 재사용함으로써 개발 비용을 대폭 절감할 수 있다.

#### 구성 요소

| MCP 서버 | 제공 기능 | 우선순위 |
|---|---|---|
| `filesystem` | 로컬 파일 읽기/쓰기/검색 | 높음 |
| `fetch` | HTTP URL 내용 가져오기 | 높음 |
| `brave-search` | 웹 검색 (Brave Search API 키 필요) | 중간 |
| `memory` | 대화 간 영구 메모리 저장 | 중간 |
| `sqlite` | SQLite DB 조회 | 낮음 |

#### MCP 연동 아키텍처

Open WebUI는 SSE(Server-Sent Events) 트랜스포트 기반 MCP만 지원한다. stdio 기반 MCP 서버(대부분의 공식 MCP 서버)는 `supergateway`를 통해 SSE로 변환해야 한다.

```
Open WebUI
    |
    | SSE (HTTP)
    v
supergateway 컨테이너 (stdio → SSE 변환 프록시)
    |
    | stdio
    v
MCP 서버 프로세스 (filesystem, fetch 등)
```

#### Docker Compose 추가 구성

```yaml
services:
  mcp-filesystem:
    image: node:20-alpine
    container_name: mcp-filesystem
    command: >
      npx -y supergateway
      --stdio "npx -y @modelcontextprotocol/server-filesystem /workspace"
      --port 8000
    volumes:
      - ./workspace:/workspace  # 에이전트가 접근할 디렉토리 (제한적으로)
    networks:
      - ai-infra
    restart: unless-stopped

  mcp-fetch:
    image: node:20-alpine
    container_name: mcp-fetch
    command: >
      npx -y supergateway
      --stdio "npx -y @modelcontextprotocol/server-fetch"
      --port 8000
    networks:
      - ai-infra
    restart: unless-stopped
```

#### 수행 작업

- [ ] Open WebUI에서 MCP 서버 URL 등록 (`http://mcp-filesystem:8000/sse`)
- [ ] Docker Compose에 MCP 컨테이너 추가
- [ ] filesystem MCP로 특정 디렉토리만 접근 가능하도록 마운트 경로 제한
- [ ] fetch MCP 동작 확인 (URL 내용 요약 테스트)
- [ ] (선택) Brave Search API 키 발급 및 brave-search MCP 연결

#### 검증 방법

- [ ] "D:/workspace/README.md 파일 내용을 요약해줘" 요청에 파일 읽기 후 응답 확인
- [ ] "https://example.com 페이지 내용 알려줘" 요청에 URL fetch 후 응답 확인
- [ ] MCP 서버 연결 상태 Open WebUI 설정 화면에서 확인

#### 특히 주의할 점

- filesystem MCP의 접근 경로를 반드시 제한한다. 전체 파일시스템 마운트는 보안상 위험하다
- MCP 서버 컨테이너 포트는 호스트에 노출하지 않는다 (Docker 내부 네트워크만 사용)
- `npx`를 통한 최초 실행 시 패키지 다운로드가 발생한다. 프리빌드 이미지 사용을 검토한다
- supergateway는 SSE 연결이 끊기면 자동 재연결이 필요하다. `restart: unless-stopped` 필수

---

### Phase 5: 고급 기능 (Pipelines, RAG 강화, 외부 벡터 DB)

**목표:** Pipelines를 활용한 미들웨어 레이어 구성, 내장 ChromaDB 한계 극복을 위한 외부 벡터 DB 연동, RAG 파이프라인 강화

**왜 이 기능들이 마지막인가?**
Pipelines와 외부 벡터 DB는 별도의 컨테이너와 설정이 필요한 고급 기능이다. 기본 에이전트 기능이 충분히 검증된 후에야 이 레이어를 추가하는 것이 복잡도 관리 측면에서 올바른 순서다.

#### 구성 요소

| 컴포넌트 | 이미지 | 역할 |
|---|---|---|
| Pipelines | `ghcr.io/open-webui/pipelines:main` | 요청/응답 미들웨어, RAG 파이프라인 |
| Qdrant | `qdrant/qdrant` | 외부 벡터 DB (ChromaDB 대체) |
| SearXNG | `searxng/searxng` | 자체 호스팅 메타 검색 엔진 |

#### Pipelines 활용 시나리오

```
사용자 입력
    → [Filter Pipeline] 입력 전처리 (욕설 필터, 언어 감지 등)
    → [Pipe Pipeline] 커스텀 RAG 파이프라인 실행
    → [Ollama] LLM 추론
    → [Filter Pipeline] 출력 후처리 (포맷 변환, 민감 정보 마스킹 등)
    → 사용자 출력
```

#### Pipelines Docker Compose 추가 구성

```yaml
services:
  pipelines:
    image: ghcr.io/open-webui/pipelines:main
    container_name: pipelines
    volumes:
      - pipelines-data:/app/pipelines
    networks:
      - ai-infra
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    volumes:
      - qdrant-data:/qdrant/storage
    networks:
      - ai-infra
    restart: unless-stopped
```

#### SearXNG 자체 검색 엔진 (Brave API 미사용 시 대안)

```yaml
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    volumes:
      - ./searxng-config:/etc/searxng
    networks:
      - ai-infra
    restart: unless-stopped
```

#### 수행 작업

- [ ] Pipelines 컨테이너 추가 및 Open WebUI 연결 설정
- [ ] 샘플 Filter Pipeline 등록 (입력 언어 감지 등)
- [ ] Qdrant 컨테이너 추가
- [ ] Open WebUI RAG 설정에서 Qdrant 엔드포인트 연결
- [ ] 문서 업로드 후 Knowledge Base 생성 및 검색 품질 테스트
- [ ] (선택) SearXNG 설치 및 웹 검색 RAG 연결

#### 검증 방법

- [ ] Pipelines 관리 화면에서 등록된 파이프라인 목록 확인
- [ ] Filter Pipeline 동작 (입력 변환 적용 여부) 확인
- [ ] Qdrant 연결 후 문서 임베딩 및 검색 결과 품질 내장 ChromaDB 대비 비교
- [ ] SearXNG를 통한 실시간 웹 검색 RAG 응답 확인

#### 특히 주의할 점

- Pipelines는 Open WebUI와 별도 컨테이너로 동작한다. `PIPELINES_URLS` 환경 변수로 연결한다
- Qdrant 전환 시 기존 ChromaDB의 임베딩 데이터는 자동 마이그레이션되지 않는다. 재인덱싱이 필요하다
- 임베딩 모델은 Ollama의 `nomic-embed-text` 또는 `mxbai-embed-large`를 사용한다 (외부 OpenAI 임베딩 API 불필요)
- SearXNG는 rate limiting 설정이 없으면 검색 엔진 차단 위험이 있다

---

## 5. 환경 요구사항

### 5.1 하드웨어 요구사항

| 항목 | 최소 사양 (CPU-only) | 권장 사양 (GPU) | 고성능 사양 |
|---|---|---|---|
| CPU | Intel/AMD 8코어 이상 | Intel/AMD 12코어 이상 | 16코어 이상 |
| RAM | 16GB | 32GB | 64GB |
| GPU | - | NVIDIA RTX 3070 (8GB) | NVIDIA RTX 3090/4090 (24GB) |
| 저장장치 | SSD 50GB 여유 | SSD 100GB 여유 | NVMe SSD 200GB+ |
| 네트워크 | 100 Mbps (초기 다운로드용) | 동일 | 동일 |

> 디스크 용량 주의: 7B 모델 ~4GB, 14B 모델 ~8GB, 32B 모델 ~20GB. 여러 모델 보유 시 100GB 이상 확보 권장

### 5.2 소프트웨어 요구사항

| 소프트웨어 | 버전 | 설치 방법 | 비고 |
|---|---|---|---|
| Windows 11 | 22H2 이상 | OS 업데이트 | WSL2 지원 필수 |
| WSL2 | 최신 | `wsl --install` | Ubuntu 22.04 LTS 권장 |
| Docker Desktop | v4.24 이상 | 공식 사이트 | GPU 지원을 위해 최신 버전 유지 |
| NVIDIA 드라이버 | v531.18 이상 | GeForce Experience 또는 공식 사이트 | GPU 사용 시에만 |
| Git | 최신 | winget 또는 공식 사이트 | 선택사항 |

### 5.3 WSL2 최적화 설정

`%USERPROFILE%\.wslconfig` 파일 생성:

```ini
[wsl2]
memory=16GB          # 시스템 RAM의 50% 수준 권장
processors=8         # 물리 코어의 50-75% 수준
swap=16GB            # 메모리와 동일하거나 2배
localhostForwarding=true

[experimental]
autoMemoryReclaim=gradual  # WSL2 메모리 자동 회수 (Windows 11 빌드 22621.2338+)
```

적용: `wsl --shutdown` 후 재시작

### 5.4 네트워크 요구사항

- 초기 설정 시 인터넷 연결 필요 (Docker 이미지 다운로드, LLM 모델 다운로드)
- 운영 중에는 인터넷 연결 불필요 (완전 로컬 동작)
- DNS 설정 이슈 시 Docker 데몬 설정에 `"dns": ["8.8.8.8", "8.8.4.4"]` 추가

---

## 6. 보안 고려사항

### 6.1 포트 노출 정책

| 원칙 | 적용 방법 | 이유 |
|---|---|---|
| Ollama API 미노출 | `ports` 섹션에 Ollama 포트 제외 | 인증 없는 API 엔드포인트로 직접 호출 시 무단 모델 사용 위험 |
| Open WebUI 로컬호스트 바인딩 | `"127.0.0.1:3000:8080"` 형식 사용 | LAN의 다른 기기에서 접근 불가 |
| MCP 서버 미노출 | Docker 내부 네트워크 전용 | 파일시스템 접근 도구가 외부에 노출되면 치명적 |

### 6.2 인증 및 접근 제어

```
체크리스트:
[ ] WEBUI_SECRET_KEY: 충분한 길이의 랜덤 문자열 사용 (32자 이상)
[ ] 관리자 계정 생성 직후 ENABLE_SIGNUP=false 설정
[ ] .env 파일을 .gitignore에 추가 (비밀 키 Git 커밋 방지)
[ ] Named Volume에 external: true 설정 (docker compose down -v 실수 방지)
[ ] Open WebUI 관리자 패널에서 모델별 접근 권한 설정
```

### 6.3 데이터 보호

- 모든 대화 기록은 `open-webui-data` Named Volume에 로컬 저장
- 텔레메트리: Open WebUI 기본 설정에서 익명 사용 통계 전송 여부 확인 및 필요 시 비활성화
- 모델 파일: `ollama-models` Named Volume에 저장, 외부 클라우드 동기화 도구의 접근 경로에서 제외 권장

### 6.4 filesystem MCP 보안

```yaml
# 안전한 마운트 예시 (특정 워크스페이스만 허용)
volumes:
  - D:/AI-Workspace:/workspace:rw  # 허용 디렉토리만 마운트
  # 절대 금지:
  # - C:/:/host  # 전체 C 드라이브 마운트
  # - D:/:/data  # 전체 D 드라이브 마운트
```

---

## 7. 리스크 및 대응 방안

### 7.1 알려진 이슈 및 트러블슈팅

| 증상 | 원인 | 해결 방법 |
|---|---|---|
| Open WebUI 접속 불가 (502 Bad Gateway) | Ollama 컨테이너 미시작 상태에서 WebUI 시작 | `depends_on` + healthcheck 설정, 또는 `docker restart open-webui` |
| 모델 다운로드 실패 (타임아웃) | DNS 해석 실패 또는 네트워크 불안정 | Docker 데몬에 DNS 서버 추가 (`8.8.8.8`), 재시도 |
| WSL2 메모리 과다 사용 | LLM 모델 메모리 미해제 | `OLLAMA_KEEP_ALIVE=1m` 설정, 주기적 `wsl --shutdown` |
| GPU 미인식 | 드라이버 버전 부족 또는 Docker Desktop 구버전 | 드라이버 v531.18+, Docker Desktop v4.24+ 업데이트 |
| Tool Calling 미동작 | Default 모드 설정 또는 모델이 Tool Calling 미지원 | Native 모드로 변경, qwen2.5:7b 이상 모델 사용 |
| 한국어 응답 품질 저하 | 모델이 한국어 최적화가 아닌 경우 | qwen2.5 계열 모델로 교체 |
| 컨테이너 재시작 후 모델 재다운로드 | Volume 설정 누락 | Named Volume 마운트 확인 |

### 7.2 성능 관련 리스크

| 리스크 | 발생 조건 | 대응 방안 |
|---|---|---|
| 응답 속도 저하 (CPU-only) | GPU 없는 환경에서 14B+ 모델 사용 | 7B Q4_K_M 모델 사용, 또는 GPU 추가 |
| 메모리 부족 (OOM) | 대용량 컨텍스트 + 대형 모델 동시 로드 | `OLLAMA_MAX_LOADED_MODELS=1` 설정, 모델 크기 다운그레이드 |
| WSL2 디스크 I/O 병목 | 바인드 마운트 사용 시 | Named Volume 사용으로 전환 (I/O 50-70% 개선) |

### 7.3 유지보수 리스크

| 리스크 | 내용 | 대응 방안 |
|---|---|---|
| 이미지 버전 불일치 | `main` 태그 이미지의 Breaking Change | 주요 업그레이드 전 변경 로그 확인, 고정 버전 태그 사용 고려 |
| Volume 데이터 손실 | `docker compose down -v` 실수 실행 | `external: true` 설정으로 방어, 정기 백업 |
| MCP 서버 호환성 | MCP 프로토콜 버전 변화 | 검증된 버전 고정, 업그레이드 전 테스트 |

### 7.4 긴급 복구 절차

```bash
# 1. 전체 서비스 재시작
docker compose down
docker compose up -d

# 2. 특정 서비스만 재시작
docker compose restart open-webui

# 3. 로그 확인
docker compose logs -f ollama
docker compose logs -f open-webui

# 4. 컨테이너 내부 진단
docker exec -it ollama bash
docker exec -it open-webui bash

# 5. WSL2 메모리 해제
wsl --shutdown
# 이후 Docker Desktop 재시작

# 6. Volume 백업 (정기 실행 권장)
docker run --rm -v open-webui-data:/data -v D:/Backup:/backup alpine \
  tar czf /backup/open-webui-backup-$(date +%Y%m%d).tar.gz /data
```

---

## 8. 향후 확장 방향

### 8.1 멀티에이전트 아키텍처

단일 에이전트에서 역할 분리된 멀티에이전트 시스템으로 확장할 수 있다.

```
[오케스트레이터 에이전트]
    |
    +-- [리서치 에이전트] → 웹 검색 MCP, fetch MCP
    |
    +-- [코드 에이전트] → qwen2.5-coder, filesystem MCP
    |
    +-- [문서 에이전트] → RAG + ChromaDB/Qdrant
    |
    +-- [실행 에이전트] → 코드 실행 샌드박스 (별도 컨테이너)
```

**구현 방향:** Open WebUI의 Pipe Pipeline을 활용하여 LLM 간 라우팅 로직 구현, 또는 LangGraph/AutoGen 같은 전용 에이전트 프레임워크를 별도 컨테이너로 추가

### 8.2 커스텀 모델 파인튜닝

| 단계 | 방법 | 도구 |
|---|---|---|
| 데이터 수집 | 도메인 특화 대화 데이터 구축 | 수동 또는 GPT-4 생성 후 검토 |
| LoRA 파인튜닝 | VRAM 16GB+ 환경에서 수행 | LLaMA-Factory, Axolotl |
| GGUF 변환 | 파인튜닝 모델을 Ollama에서 사용 가능한 형식으로 변환 | llama.cpp |
| Ollama 등록 | `Modelfile`로 커스텀 모델 등록 | Ollama CLI |

### 8.3 프로덕션 전환 고려사항

로컬 개발 환경에서 팀 공유 또는 프로덕션으로 전환할 경우:

| 항목 | 로컬 설정 | 프로덕션 전환 시 |
|---|---|---|
| 인증 | 단일 사용자 | Keycloak 또는 Authentik 연동 (OIDC) |
| 호스팅 | localhost | 역방향 프록시 (Nginx/Caddy) + TLS |
| 모델 서빙 | 단일 Ollama | 멀티 GPU 서버 또는 vLLM으로 교체 |
| 모니터링 | Docker logs | Prometheus + Grafana 스택 |
| 스케일링 | 단일 컨테이너 | Kubernetes 또는 Docker Swarm |
| 백업 | 수동 | 자동화된 스냅샷 정책 |

### 8.4 개발 생산성 향상 아이디어

- **VS Code 통합**: Continue.dev 익스텐션 + Ollama 백엔드 연결로 로컬 코드 어시스턴트 구현
- **자동화 에이전트**: n8n 또는 Activepieces를 Open WebUI와 연동하여 워크플로우 자동화
- **음성 인터페이스**: Whisper 기반 STT + TTS 컨테이너를 추가하여 음성 대화 에이전트 구현
- **모니터링 대시보드**: Ollama의 모델 사용량, 응답 시간, 토큰 처리량 메트릭 수집 및 시각화

---

## 부록: 프로젝트 디렉토리 구조

```
D:\Dev\My-AI-Lab\ai-infra-hub\
|
+-- CLAUDE.md                    # Claude Code 프로젝트 지침
+-- .env                         # 환경 변수 (Git 제외 대상)
+-- .env.example                 # 환경 변수 샘플 (Git 포함)
+-- .gitignore
+-- docker-compose.yml           # Phase 1-2: 기본 구성
+-- docker-compose.gpu.yml       # Phase 2: GPU 오버라이드
+-- docker-compose.mcp.yml       # Phase 4: MCP 서버 추가
+-- docker-compose.advanced.yml  # Phase 5: Pipelines, Qdrant 등
|
+-- docs\
|   +-- PRD.md                   # 이 문서
|   +-- setup-guide.md           # 단계별 설치 가이드 (추후 작성)
|   +-- troubleshooting.md       # 트러블슈팅 모음 (추후 작성)
|
+-- tools\                       # Open WebUI Tool 소스
|   +-- datetime_tool.py
|   +-- calculator_tool.py
|
+-- pipelines\                   # Phase 5: Pipelines 소스
|   +-- filter_pipeline.py
|
+-- workspace\                   # filesystem MCP 접근 허용 디렉토리
    +-- .gitkeep
```

---

## 9. 버전 관리 정책

### 9.1 GitHub 리포지토리

- **원격 저장소:** https://github.com/dongle94/ai-infra-hub
- **기본 브랜치:** `main`

### 9.2 커밋 정책

각 Phase 내에서 기능 단위 작업이 완료될 때마다 커밋한다. 한 번에 모든 작업을 몰아서 커밋하지 않는다.

**Phase별 커밋 단위 예시:**

| Phase | 커밋 단위 | 커밋 메시지 예시 |
|---|---|---|
| Phase 1 | docker-compose.yml 작성 | `feat: add docker-compose for Ollama + Open WebUI` |
| Phase 1 | .env.example, .gitignore 구성 | `chore: add env template and gitignore` |
| Phase 2 | GPU 설정 추가 | `feat: enable GPU passthrough for Ollama` |
| Phase 3 | Tool 코드 작성 (도구별 각각) | `feat: add datetime tool for agent` |
| Phase 4 | MCP 서버 구성 추가 | `feat: add MCP filesystem server config` |
| Phase 5 | Pipelines 구성 추가 | `feat: add Pipelines and Qdrant services` |

**커밋 메시지 규칙 (Udacity Commit Convention):**

Prefix 종류:
- `feat:` 새로운 기능 추가
- `fix:` 버그 수정
- `docs:` 문서 변경
- `chore:` 설정, 빌드, 패키지 등 코드 외 관리 작업
- `refactor:` 기능 변경 없는 코드 구조 개선
- `test:` 테스트 추가/수정

메시지 구조:
```
<prefix>: <타이틀 (영문, 간결하게)>

- 세부항목 1 (한국어)
- 세부항목 2 (한국어)

- detail 1 (English)
- detail 2 (English)
```

예시:
```
feat: add docker-compose for Ollama + Open WebUI

- Ollama + Open WebUI 2-컨테이너 기본 구성
- Named Volume 및 사용자 정의 브리지 네트워크 설정
- 환경 변수 .env 분리

- Add 2-container setup with Ollama and Open WebUI
- Configure named volumes and custom bridge network
- Separate environment variables into .env file
```

주의사항:
- 설정 파일에 민감 정보(`.env`)가 포함되지 않았는지 커밋 전 반드시 확인

### 9.3 커밋 체크리스트

매 커밋 전 확인:

- [ ] `.env` 파일이 staging에 포함되지 않았는가
- [ ] `docker compose up -d`로 정상 동작 확인했는가 (해당되는 경우)
- [ ] 변경 사항이 하나의 기능 단위에 해당하는가

---

*이 문서는 프로젝트 진행에 따라 지속적으로 업데이트됩니다.*
*마지막 수정: 2026-02-12*
