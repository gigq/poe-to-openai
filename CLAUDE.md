# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
- **Development**: `python3 run.py` - Runs FastAPI app via uvicorn on port 39527
- **Production**: `./run.sh` - Runs with gunicorn (configurable workers/timeout via CORE_NUM/TIME_OUT env vars)
- **Quick start**: `./start.sh` - Simple wrapper script for development

### Dependencies
- **Install**: `pip install -r requirements.txt`
- **Key dependency**: `fastapi_poe==0.0.53` (POE API client)

### Testing
- **Manual testing**: Use `test-api.http` file with HTTP client
- No automated test framework configured

### API Testing Examples

#### OpenAI Chat Completions
```bash
# Non-streaming
curl -X POST http://localhost:39527/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ctok" \
  -d '{
    "model": "o3",
    "messages": [
      {"role": "user", "content": "Write a short poem about coding"}
    ],
    "stream": false
  }'

# Streaming
curl -X POST http://localhost:39527/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer ctok" \
  -d '{
    "model": "o3",
    "messages": [
      {"role": "user", "content": "Write a short poem about coding"}
    ],
    "stream": true
  }'
```

#### Ollama Chat API
```bash
# Non-streaming
curl -X POST http://localhost:39527/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ctok" \
  -d '{
    "model": "o3",
    "messages": [
      {"role": "user", "content": "Write a short poem about coding"}
    ],
    "stream": false
  }'

# Streaming
curl -X POST http://localhost:39527/api/chat \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "Authorization: Bearer ctok" \
  -d '{
    "model": "o3",
    "messages": [
      {"role": "user", "content": "Write a short poem about coding"}
    ],
    "stream": true
  }'
```

## Architecture Overview

This is a **multi-protocol API bridge** that converts POE.com API into OpenAI and Ollama compatible interfaces.

### Core Request Flow
1. **Authentication Layer** (`route/route_*.py:get_token_from_request`) - Maps custom tokens to system POE tokens via env vars
2. **Protocol Translation** (`api/poe_api.py:openai_message_to_poe_message`) - Converts request formats to POE ProtocolMessage
3. **Model Mapping** (`api/poe_api.py:get_bot`) - Maps external model names to POE bot names via MODEL_MAPPING env var
4. **POE API Client** (`api/poe_api.py`) - Uses `fastapi_poe.client` for actual API calls
5. **Response Formatting** - Converts POE responses back to target API format

### API Compatibility Layers
- **OpenAI API** (`route/route_chat.py`, `route/route_image.py`):
  - `/v1/chat/completions` - Chat with streaming support
  - `/v1/images/generations` - Image generation via POE image bots
  - `/v1/models` - Available models list
  
- **Ollama API** (`route/route_ollama.py`):
  - `/api/generate` - Single prompt completion
  - `/api/chat` - Multi-turn conversation
  - `/api/tags` - Models list in Ollama format

### Configuration Architecture
- **Environment-driven**: All tokens, model mappings, and proxy settings via env vars
- **Model Mapping**: JSON string in MODEL_MAPPING env var maps external model names to POE bot names
- **Proxy Support**: HTTP/SOCKS5 proxy configuration for POE API calls
- **Token System**: CUSTOM_TOKEN (external auth) maps to SYSTEM_TOKEN (POE API key)

### Key Implementation Details
- **Streaming**: Both OpenAI and Ollama support real-time response streaming via AsyncGenerator
- **CORS**: Custom middleware handles cross-origin requests with dynamic origin headers
- **Response Formatting**: Each API has distinct response schemas with fake timing/usage metadata
- **Error Handling**: Invalid models fall back to defaults (typically GPT-4o)

### File Structure by Responsibility
- `main.py` - FastAPI app setup, CORS middleware, router registration
- `route/` - Protocol-specific endpoint handlers (OpenAI, Ollama, Image)
- `api/poe_api.py` - POE API client wrapper and message translation
- `util/utils.py` - Shared utilities (random string generation, etc.)

The architecture enables existing OpenAI/Ollama clients to transparently use POE's models without code changes.