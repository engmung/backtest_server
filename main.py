import os
import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 모듈화된 컴포넌트 임포트
from scheduler import setup_scheduler, simulate_scheduler_at_time
from notion_utils import query_notion_database, REFERENCE_DB_ID

app = FastAPI(title="YouTube Script Extractor with Notion Integration")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class NotionSyncRequest(BaseModel):
    pass  # 빈 요청 본문, 단순히 동기화 작업 트리거용

class NotionSyncResponse(BaseModel):
    status: str
    message: str

@app.get("/")
async def root():
    return {"message": "YouTube Script Extractor with Notion Integration"}

@app.post("/sync-notion-db", response_model=NotionSyncResponse)
async def sync_notion_db(background_tasks: BackgroundTasks):
    """참고용 DB의 모든 채널에 대해 스크립트를 추출하고 스크립트 DB에 저장합니다."""
    from youtube_utils import process_channel_url, get_video_transcript
    
    try:
        # 참고용 DB의 모든 페이지 가져오기
        reference_pages = await query_notion_database(REFERENCE_DB_ID)
        logger.info(f"Found {len(reference_pages)} channels in reference database")
        
        if not reference_pages:
            return {"status": "warning", "message": "참고용 DB에서 채널을 가져올 수 없습니다."}
        
        # 백그라운드 작업으로 실행
        background_tasks.add_task(process_channels_manually, reference_pages)
        return {"status": "processing", "message": "동기화 작업이 시작되었습니다. 완료까지 시간이 걸릴 수 있습니다."}
    
    except Exception as e:
        logger.error(f"데이터베이스 동기화 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"데이터베이스 동기화 중 오류가 발생했습니다: {str(e)}")

@app.post("/test-scheduler")
async def test_scheduler(test_time: Dict[str, Any]):
    """
    특정 시간을 시뮬레이션하여 스케줄러 테스트
    
    요청 본문 예시: 
    {
        "hour": 9,
        "minute": 0,
        "weekday": 0,  # 0=월요일, 6=일요일
        "simulate_only": true  # true=동작만 확인, false=실제 실행
    }
    """
    hour = test_time.get("hour", datetime.now().hour)
    minute = test_time.get("minute", 0)
    weekday = test_time.get("weekday", datetime.now().weekday())
    simulate_only = test_time.get("simulate_only", True)
    
    result = await simulate_scheduler_at_time(hour, minute, weekday, simulate_only)
    return {"status": "success", "simulated_time": f"{hour:02d}:{minute:02d}", "weekday": weekday, "result": result}

async def process_channels_manually(reference_pages):
    """참고용 DB의 모든 채널을 수동으로 처리합니다."""
    from scheduler import process_channel
    
    processed_count = 0
    
    for page in reference_pages:
        try:
            success = await process_channel(page)
            if success:
                processed_count += 1
        except Exception as e:
            logger.error(f"채널 처리 중 오류: {str(e)}")
    
    logger.info(f"{len(reference_pages)}개의 채널 중 {processed_count}개의 새 스크립트를 추출했습니다.")

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 스케줄러 설정"""
    setup_scheduler()
    logger.info("Application started with scheduler configured")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)