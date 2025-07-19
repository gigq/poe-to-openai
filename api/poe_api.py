import json
import logging
import os

import httpx
from fastapi import Form
from fastapi.responses import JSONResponse
from fastapi_poe.client import get_bot_response, get_final_response, QueryRequest
from fastapi_poe.types import ProtocolMessage

timeout = 500

logging.basicConfig(level=logging.DEBUG)

client_dict = {}


async def get_responses(api_key, prompt=[], bot=""):
    bot_name = bot
    # "system", "user", "bot"
    messages = openai_message_to_poe_message(prompt)
    print("=================", messages, "=================")

    additional_params = {"temperature": 0.7, "skip_system_prompt": False, "logit_bias": {}, "stop_sequences": []}
    query = QueryRequest(
        query=messages,
        user_id="",
        conversation_id="",
        message_id="",
        version="1.0",
        type="query",
        **additional_params
    )

    session = create_client()
    return await get_final_response(query, bot_name=bot_name, api_key=api_key, session=session)


def is_thinking_token(text):
    """Check if the text is a 'Thinking...' token that should be filtered out"""
    if not text:
        return False
    # Filter both "Thinking... (Xs elapsed)" and plain "Thinking..." tokens
    if text.startswith("Thinking...") and ("elapsed" in text or text.strip() == "Thinking..."):
        return True
    # Filter Gemini-style thinking tokens that start with "*Thinking...*" or contain "> **" patterns
    if text.startswith("*Thinking...*") or "> **" in text:
        return True
    return False

async def stream_get_responses(api_key, prompt, bot):
    bot_name = bot
    messages = openai_message_to_poe_message(prompt)

    session = create_client()
    async for partial in get_bot_response(messages=messages, bot_name=bot_name, api_key=api_key,
                                          skip_system_prompt=False, session=session):
        if not is_thinking_token(partial.text):
            yield partial.text


async def get_image(api_key, prompt, bot="dall-e-3"):
    """
    使用Poe API生成图像
    
    Args:
        api_key: Poe API密钥
        prompt: 图像生成提示词
        bot: 要使用的图像生成机器人名称
        
    Returns:
        生成的图像URL
    """
    bot_name = get_bot(bot)
    message = ProtocolMessage(role="user", content=prompt)
    
    session = create_client()
    logging.info(f"发送图像生成请求到 {bot_name}，提示词: {prompt}")
    
    result = ""
    async for partial in get_bot_response(messages=[message], bot_name=bot_name, api_key=api_key,
                                          skip_system_prompt=False, session=session):
        # 保存最终结果
        if partial.text and (partial.text.startswith("![") or "http" in partial.text):
            result = partial.text
            logging.info(f"收到图像结果: {result}")
    
    return result


def add_token(token: str):
    if token not in client_dict:
        try:
            client_dict[token] = token
            return "ok"
        except Exception as exception:
            logging.info("Failed to connect to poe due to " + str(exception))
            return "failed: " + str(exception)
    else:
        return "exist"


def get_bot(model):
    model_mapping = json.loads(os.environ.get("MODEL_MAPPING", "{}"))
    return model_mapping.get(model, "Unknown Model")


def openai_message_to_poe_message(messages=[]):
    new_messages = []
    for message in messages:
        role = message["role"]
        if role == 'developer':
            continue
        if role == "assistant":
            role = "bot"

        # Handle content properly based on its type
        content = message["content"]
        if isinstance(content, list):
            # Process the list of content parts
            processed_content = ""
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        processed_content += item.get("text", "")
                    # Handle other types as needed
                else:
                    processed_content += str(item)
            content = processed_content
        elif not isinstance(content, str):
            content = str(content)

        new_messages.append(ProtocolMessage(role=role, content=content))
    return new_messages

def create_client():
    proxy_config = {
        "proxy_type": os.environ.get("PROXY_TYPE"),
        "proxy_host": os.environ.get("PROXY_HOST"),
        "proxy_port": os.environ.get("PROXY_PORT"),
        "proxy_username": os.environ.get("PROXY_USERNAME"),
        "proxy_password": os.environ.get("PROXY_PASSWORD"),
    }

    proxy = create_proxy(proxy_config)
    client = httpx.AsyncClient(timeout=600, proxies=proxy)
    return client


def create_proxy(proxy_config):
    proxy_type = proxy_config["proxy_type"]
    proxy_url = create_proxy_url(proxy_config)

    if proxy_type in ["http", "socks"] and proxy_url:
        return {
            "http://": proxy_url,
            "https://": proxy_url,
        }
    else:
        return None


def create_proxy_url(proxy_config):
    proxy_type = proxy_config["proxy_type"]
    proxy_host = proxy_config["proxy_host"]
    proxy_port = proxy_config["proxy_port"]
    proxy_username = proxy_config["proxy_username"]
    proxy_password = proxy_config["proxy_password"]

    if not proxy_host or not proxy_port:
        return None

    if proxy_type == "http":
        return f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
    elif proxy_type == "socks":
        return f"socks5://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
    else:
        return None
