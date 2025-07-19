import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api import poe_api
from util import utils

logger = logging.getLogger(__name__)

router = APIRouter()
load_dotenv()


@router.post("/api/generate")
async def ollama_generate(request: Request):
    """
    Ollama generate endpoint - single prompt completion
    """
    body = await request.json()
    model, prompt, stream, format_type, options = parse_generate_request(body)
    
    if model is None or prompt is None:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    token = await get_token_from_request(request)
    
    # Convert single prompt to messages format for Poe
    messages = [{"role": "user", "content": prompt}]
    
    if stream:
        return StreamingResponse(
            process_ollama_generate_stream(model, messages, token, format_type),
            media_type="application/x-ndjson"
        )
    else:
        return await process_ollama_generate_response(model, messages, token, format_type)


@router.post("/api/chat")
async def ollama_chat(request: Request):
    """
    Ollama chat endpoint - conversation with message history
    """
    body = await request.json()
    model, messages, stream, format_type, options = parse_chat_request(body)
    
    if model is None or not messages:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    token = await get_token_from_request(request)
    
    if stream:
        return StreamingResponse(
            process_ollama_chat_stream(model, messages, token, format_type),
            media_type="application/x-ndjson"
        )
    else:
        return await process_ollama_chat_response(model, messages, token, format_type)


@router.get("/api/tags")
async def ollama_tags():
    """
    Ollama tags endpoint - list available models
    """
    models = get_available_models()
    return JSONResponse(content={"models": models})


def parse_generate_request(body: Dict[str, Any]):
    """Parse Ollama generate request body"""
    try:
        model = body.get('model')
        prompt = body.get('prompt')
        stream = body.get('stream', True)  # Ollama defaults to streaming
        format_type = body.get('format')
        options = body.get('options', {})
        
        return model, prompt, stream, format_type, options
    except Exception as e:
        logger.error(f"Error parsing generate request: {e}")
        return None, None, None, None, None


def parse_chat_request(body: Dict[str, Any]):
    """Parse Ollama chat request body"""
    try:
        model = body.get('model')
        messages = body.get('messages', [])
        stream = body.get('stream', True)  # Ollama defaults to streaming
        format_type = body.get('format')
        options = body.get('options', {})
        
        return model, messages, stream, format_type, options
    except Exception as e:
        logger.error(f"Error parsing chat request: {e}")
        return None, None, None, None, None


async def get_token_from_request(request: Request):
    """Get token from request headers (same as other routes)"""
    logger.info("Getting token for Ollama request")
    auth_header = request.headers.get('Authorization', '')
    
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
    else:
        token = auth_header

    # Custom token
    custom_token = os.environ.get('CUSTOM_TOKEN')
    # Built-in token
    system_token = os.environ.get('SYSTEM_TOKEN')

    if token == custom_token:
        return system_token
    
    # If no token provided, use system token as fallback
    if not token:
        return system_token

    return token


def get_available_models() -> List[Dict[str, Any]]:
    """Get list of available models in Ollama format"""
    # Use the same models as defined in route_chat.py with detailed info
    model_configs = [
        {"name": "Gemini-2.5-Pro", "size": 4800000000, "param_size": "8B", "family": "gemini"},
        {"name": "Grok-4", "size": 7200000000, "param_size": "12B", "family": "grok"},
        {"name": "GPT-4o", "size": 8000000000, "param_size": "175B", "family": "gpt"},
        {"name": "GPT-4o-search", "size": 8500000000, "param_size": "175B", "family": "gpt"},
        {"name": "o3", "size": 9000000000, "param_size": "200B", "family": "gpt"},
        {"name": "o3-pro", "size": 12000000000, "param_size": "300B", "family": "gpt"},
        {"name": "o4-mini", "size": 2000000000, "param_size": "3B", "family": "gpt"},
        {"name": "o4-mini-deep-research", "size": 3000000000, "param_size": "7B", "family": "gpt"},
        {"name": "Claude-Sonnet-4", "size": 6000000000, "param_size": "100B", "family": "claude"},
        {"name": "Claude-Opus-4", "size": 8000000000, "param_size": "175B", "family": "claude"},
        {"name": "Claude-Sonnet-4-Reasoning", "size": 7000000000, "param_size": "120B", "family": "claude"},
        {"name": "Claude-Opus-4-Reasoning", "size": 9000000000, "param_size": "200B", "family": "claude"}
    ]
    
    models = []
    current_time = datetime.now().isoformat() + "Z"
    
    for model_config in model_configs:
        # Generate consistent digest for each model
        model_name = model_config["name"]
        digest_seed = f"{model_name}_{model_config['param_size']}"
        digest = f"sha256:{hash(digest_seed) & 0xffffffffffff:012x}"
        
        # Create complete Ollama-style model entry
        model_entry = {
            "name": model_name,
            "model": model_name,
            "modified_at": current_time,
            "size": model_config["size"],
            "digest": digest,
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": model_config["family"],
                "families": [model_config["family"]],
                "parameter_size": model_config["param_size"],
                "quantization_level": "Q4_0"
            }
        }
        models.append(model_entry)
    
    return models


def get_poe_model_mapping(model: str) -> str:
    """Get Poe model name from Ollama model name with fallback"""
    # Try environment variable first
    poe_model = poe_api.get_bot(model)
    if poe_model != "Unknown Model":
        return poe_model
    
    # Fallback mapping for common models
    fallback_mapping = {
        "Gemini-2.5-Pro": "Gemini-2.5-Pro",
        "Grok-4": "Grok-4",
        "GPT-4o": "GPT-4o",
        "GPT-4o-search": "GPT-4o-search",
        "o3": "o3",
        "o3-pro": "o3-pro", 
        "o4-mini": "o4-mini",
        "o4-mini-deep-research": "o4-mini-deep-research",
        "Claude-Sonnet-4": "Claude-Sonnet-4",
        "Claude-Opus-4": "Claude-Opus-4",
        "Claude-Sonnet-4-Reasoning": "Claude-Sonnet-4-Reasoning",
        "Claude-Opus-4-Reasoning": "Claude-Opus-4-Reasoning"
    }
    
    return fallback_mapping.get(model, "GPT-4o")  # Default to GPT-4o


async def process_ollama_generate_stream(model: str, messages: List[Dict], token: str, format_type: Optional[str]):
    """Process streaming generate response"""
    poe_model = get_poe_model_mapping(model)
    
    async for result in poe_api.stream_get_responses(token, messages, poe_model):
        response_data = format_ollama_stream_response(model, result, False)
        yield f"{json.dumps(response_data)}\n"
    
    # Send final response with done=True
    final_response = format_ollama_stream_response(model, "", True)
    yield f"{json.dumps(final_response)}\n"


async def process_ollama_generate_response(model: str, messages: List[Dict], token: str, format_type: Optional[str]):
    """Process non-streaming generate response"""
    poe_model = get_poe_model_mapping(model)
    result = await poe_api.get_responses(token, messages, poe_model)
    
    response_data = format_ollama_final_response(model, result)
    return JSONResponse(content=response_data)


async def process_ollama_chat_stream(model: str, messages: List[Dict], token: str, format_type: Optional[str]):
    """Process streaming chat response"""
    poe_model = get_poe_model_mapping(model)
    
    async for result in poe_api.stream_get_responses(token, messages, poe_model):
        response_data = format_ollama_stream_response(model, result, False)
        yield f"{json.dumps(response_data)}\n"
    
    # Send final response with done=True
    final_response = format_ollama_stream_response(model, "", True)
    yield f"{json.dumps(final_response)}\n"


async def process_ollama_chat_response(model: str, messages: List[Dict], token: str, format_type: Optional[str]):
    """Process non-streaming chat response"""
    poe_model = get_poe_model_mapping(model)
    result = await poe_api.get_responses(token, messages, poe_model)
    
    response_data = format_ollama_final_response(model, result)
    return JSONResponse(content=response_data)


def format_ollama_stream_response(model: str, content: str, done: bool) -> Dict[str, Any]:
    """Format response in Ollama streaming format"""
    current_time = datetime.now().isoformat() + "Z"
    
    response = {
        "model": model,
        "created_at": current_time,
        "response": content,
        "done": done
    }
    
    if done:
        # Add completion stats for final response
        response.update({
            "total_duration": 1000000000,  # 1 second in nanoseconds (fake)
            "load_duration": 100000000,   # 100ms in nanoseconds (fake)
            "prompt_eval_count": 10,      # fake token count
            "prompt_eval_duration": 200000000,  # 200ms in nanoseconds (fake)
            "eval_count": 50,             # fake token count
            "eval_duration": 800000000    # 800ms in nanoseconds (fake)
        })
    
    return response


def format_ollama_final_response(model: str, content: str) -> Dict[str, Any]:
    """Format final response in Ollama format"""
    current_time = datetime.now().isoformat() + "Z"
    
    return {
        "model": model,
        "created_at": current_time,
        "response": content,
        "done": True,
        "total_duration": 1000000000,  # 1 second in nanoseconds (fake)
        "load_duration": 100000000,   # 100ms in nanoseconds (fake)  
        "prompt_eval_count": 10,      # fake token count
        "prompt_eval_duration": 200000000,  # 200ms in nanoseconds (fake)
        "eval_count": 50,             # fake token count
        "eval_duration": 800000000    # 800ms in nanoseconds (fake)
    }