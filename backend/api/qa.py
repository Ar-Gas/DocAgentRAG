"""QA API - 文档问答端点"""
from uuid import uuid4

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
import json

from app.core.logger import logger
from app.services.qa_service import QAService
from app.schemas.qa import QARequest
from api import success, BusinessException

router = APIRouter()
qa_service = QAService()


@router.post("/", summary="文档问答")
async def answer_question(request: QARequest):
    """
    基于选定的文档进行问答

    Args:
        request: 问答请求（query + 文档ID）

    Returns:
        问答结果和引用
    """
    try:
        if not request.query or not request.query.strip():
            raise BusinessException(400, "query 不能为空")

        session_id = request.session_id or str(uuid4())
        result = await qa_service.answer(
            query=request.query,
            doc_ids=request.doc_ids,
            top_k=request.top_k,
            session_id=session_id,
        )
        result.setdefault("session_id", session_id)

        return success(data=result, message="问答完成")

    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"问答失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/stream", summary="流式文档问答")
async def answer_question_stream(request: QARequest):
    """
    流式问答（SSE）

    前端可以通过 EventSource 接收流式答案
    """
    try:
        if not request.query or not request.query.strip():
            raise BusinessException(400, "query 不能为空")

        session_id = request.session_id or str(uuid4())

        async def generate():
            try:
                async for chunk in qa_service.answer_stream(
                    query=request.query,
                    doc_ids=request.doc_ids,
                    session_id=session_id,
                    top_k=request.top_k,
                ):
                    # SSE 格式
                    yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

                # 发送完成信号
                yield f"data: {json.dumps({'status': 'complete', 'session_id': session_id}, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"流式问答错误: {str(e)}")
                yield f"data: {json.dumps({'error': str(e), 'session_id': session_id}, ensure_ascii=False)}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"流式问答失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/{session_id}", summary="获取问答会话")
async def get_qa_session(session_id: str):
    """获取某个问答会话的详细信息"""
    try:
        session = qa_service.qa_session_repo.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        return success(data=session, message="获取会话成功")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("", summary="获取问答会话列表")
async def list_qa_sessions(
    doc_id: str = Query(None, description="限制到某个文档"),
    limit: int = Query(20, ge=1, le=100)
):
    """获取问答会话列表"""
    try:
        if doc_id:
            sessions = qa_service.qa_session_repo.list_by_doc(doc_id, limit=limit)
        else:
            sessions = qa_service.qa_session_repo.list_recent(limit=limit)

        return success(
            data={"items": sessions, "total": len(sessions)},
            message="获取会话列表成功"
        )

    except Exception as e:
        logger.error(f"获取会话列表失败: {str(e)}")
        raise BusinessException(500, detail=str(e))
