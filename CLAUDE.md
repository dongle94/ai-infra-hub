# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local LLM infrastructure hub — Ollama 기반 로컬 LLM 서빙과 Open WebUI를 활용한 로컬 AI 에이전트 구현 프로젝트.

### Core Components (Planned)

- **Ollama**: 로컬 LLM 서빙 엔진
- **Open WebUI**: 웹 기반 LLM 인터페이스 (채팅 UI, 에이전트 구성)
- **Local Agent**: 로컬 환경에서 동작하는 AI 에이전트

## Architecture

```
[Open WebUI (Frontend)] → [Ollama API (localhost:11434)] → [Local LLM Models]
                        → [Agent Layer] → [Tools / Functions]
```

## Key APIs

- Ollama API: `http://localhost:11434` (OpenAI-compatible endpoint: `/v1/chat/completions`)
- Open WebUI: `http://localhost:3000` (default)

## Development Notes

- Windows 11 환경 기반 개발
- 한국어 사용 프로젝트
