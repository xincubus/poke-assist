"""
聊天路由：聊天、流式聊天、标题生成
"""
import asyncio
import concurrent.futures
import json
import queue as _queue
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas import ChatRequest, TitleRequest

router = APIRouter(prefix="/api", tags=["聊天"])

# 服务引用（由 init_services 设置）
_chat_service = None
_llm_service = None
_auth_router = None  # auth router 模块，用于调用 _get_user_id_optional


def init_services(chat_service, llm_service, auth_router):
    """注入服务实例"""
    global _chat_service, _llm_service, _auth_router
    _chat_service = chat_service
    _llm_service = llm_service
    _auth_router = auth_router


@router.post("/chat")
async def chat(request: ChatRequest, raw_request: Request):
    """
    智能聊天接口

    根据用户消息自动判断是查询还是计算，并返回相应结果
    """
    try:
        user_id = _auth_router._get_user_id_optional(raw_request)
        result = _chat_service.process_message(
            message=request.message,
            context=request.context,
            model=request.model,
            tool_model=request.tool_model,
            debug=request.debug or False,
            platform=request.platform,
            user_id=user_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/title")
async def generate_title(request: TitleRequest):
    """
    根据对话内容生成标题（用工具调用模型，快速低成本）
    """
    if not _llm_service:
        return {"success": False, "title": ""}
    try:
        # 每条消息截断 200 字，总体截断避免 token 过多
        conversation_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
            for m in request.messages
        )
        # 总长度限制 2000 字符
        if len(conversation_text) > 2000:
            conversation_text = conversation_text[:2000] + "\n..."
        result = _llm_service.client.chat.completions.create(
            model=_llm_service.default_model,
            max_tokens=30,
            messages=[
                {"role": "system", "content": "根据以下对话内容，生成一个简短的中文标题（不超过15个字，不加引号，不加标点）。只输出标题本身。"},
                {"role": "user", "content": conversation_text}
            ]
        )
        title = result.choices[0].message.content.strip()
        return {"success": True, "title": title}
    except Exception as e:
        return {"success": False, "title": "", "error": str(e)}


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, raw_request: Request):
    """
    流式聊天接口（SSE）

    逐字推送回复内容，客户端通过 text/event-stream 接收
    计算期间每 3 秒发送心跳，防止连接超时断开
    """
    user_id = _auth_router._get_user_id_optional(raw_request)

    async def event_generator():
        try:
            # 在后台线程执行同步计算，同时发送心跳保持连接
            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

            progress_queue = _queue.Queue()

            def on_progress(step, label, detail, status):
                progress_queue.put(("progress", {"step": step, "label": label, "detail": detail, "status": status}))

            def on_thinking(call_name, reasoning_text, step=None):
                progress_queue.put(("thinking", {"source": call_name, "text": reasoning_text, "step": step}))

            future = loop.run_in_executor(
                executor,
                lambda: _chat_service.process_message(
                    message=request.message,
                    context=request.context,
                    model=request.model,
                    tool_model=request.tool_model,
                    platform=request.platform,
                    user_id=user_id,
                    progress_callback=on_progress,
                    thinking_callback=on_thinking,
                )
            )

            # 等待计算完成：100ms 轮询进度队列，每 ~3s 发一次心跳
            heartbeat_counter = 0
            while not future.done():
                # 先排空进度队列
                while not progress_queue.empty():
                    evt_type, payload = progress_queue.get_nowait()
                    yield f"event: {evt_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if heartbeat_counter % 30 == 0:
                    yield ": heartbeat\n\n"
                heartbeat_counter += 1
                try:
                    await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

            # 排空剩余进度事件
            while not progress_queue.empty():
                evt_type, payload = progress_queue.get_nowait()
                yield f"event: {evt_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            result = future.result()
            response_text = result.get("response", "抱歉，我无法处理这个请求。")
            # 去掉 LLM 可能输出的 markdown 加粗/标题符号
            response_text = re.sub(r'\*{1,3}', '', response_text)
            response_text = re.sub(r'^#{1,6}\s*', '', response_text, flags=re.MULTILINE)

            # 逐字推送，但 markdown 链接整块发送（避免半成品链接闪烁）
            i = 0
            while i < len(response_text):
                # 检测 markdown 链接起始 [
                if response_text[i] == '[':
                    m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', response_text[i:])
                    if m:
                        chunk = m.group(0)
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.02)
                        i += len(chunk)
                        continue
                yield f"data: {json.dumps(response_text[i], ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
                i += 1

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: 出错了：{str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
