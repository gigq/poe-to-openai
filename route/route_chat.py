import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api import poe_api
from util import utils

app = FastAPI()
logger = logging.getLogger(__name__)

router = APIRouter()
load_dotenv()


@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.get("/v1/models")
async def get_models():
    models = [
        {"id": "Gemini-2.5-Pro", "object": "model"},
        {"id": "Grok-4", "object": "model"},
        {"id": "GPT-4o", "object": "model"},
        {"id": "GPT-4o-search", "object": "model"},
        {"id": "o3", "object": "model"},
        {"id": "o3-pro", "object": "model"},
        {"id": "o4-mini", "object": "model"},
        {"id": "o4-mini-deep-research", "object": "model"},
        {"id": "Claude-Sonnet-4", "object": "model"},
        {"id": "Claude-Opus-4", "object": "model"},
        {"id": "Claude-Sonnet-4-Reasoning", "object": "model"},
        {"id": "Claude-Opus-4-Reasoning", "object": "model"},
    ]
    return {"data": models}

@router.post("/v1/chat/completions")
async def chat_proxy(request: Request):
    body = await request.json()
    model, messages, stream = parse_request_body(body)
    if model is None:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    token = await get_token_from_request(request)

    if stream:
        return StreamingResponse(process_openai_response_event_stream(model, messages, token),
                                 media_type="text/event-stream")
    else:
        return await default_response(model, messages, token)


def parse_request_body(body):
    try:
        model = body.get('model', 'gpt-3.5-turbo')
        messages = body.get('messages', [])
        stream = body.get('stream', False)

        return model, messages, stream
    except json.JSONDecodeError as e:
        logger.debug(f"请求体解析错误: {e}")
        return None, None, None


async def get_token_from_request(request_data):
    logger.info("请求头: %s", request_data.headers)
    logger.info("开始获取token")
    token = request_data.headers.get('Authorization', '').replace('Bearer ', '')

    # 自定义token
    custom_token = os.environ.get('CUSTOM_TOKEN')
    # 内置token
    system_token = os.environ.get('SYSTEM_TOKEN')

    if token == custom_token:
        return system_token

    return token


async def process_openai_response_event_stream(model, messages, token):
    async for result in poe_api.stream_get_responses(token, messages, model):
        result_line = f"data: {json.dumps(web_response_to_api_response_stream(result, model))}\n\n"
        yield result_line
    # 通知结束
    yield f"data: {json.dumps(web_response_to_api_response_stream('', model, True))}\n\n"
    # 通知结束
    yield "data: [DONE]\n\n"

def web_response_to_api_response_stream(result, model, stop=None):
    data = {
        "id": f"chatcmpl-{int(datetime.now().timestamp())}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "system_fingerprint": f"fp_{utils.get_8_random_str()}",
        "choices": [{
            "index": 0,
            "delta": {"content": f"{result}"},
            "finish_reason": "stop" if stop else None
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 100}
    }

    logger.debug("openai 返回数据: %s", json.dumps(data, indent=2, ensure_ascii=False))

    return data


async def default_response(model, messages, token):
    result = await poe_api.get_responses(token, messages, model)

    data = web_response_to_api_response(model, result)

    return JSONResponse(content=data)


def web_response_to_api_response(model, result):
    data = {
        "id": f"chatcmpl-{int(datetime.now().timestamp())}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "system_fingerprint": f"fp_{utils.get_8_random_str()}",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": f"{result}"},
            "logprobs": None,
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 100}
    }

    logger.debug("openai 返回数据: %s", json.dumps(data, indent=2, ensure_ascii=False))

    return data
