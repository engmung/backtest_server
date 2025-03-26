import logging
import asyncio
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Dict, Any, List, Optional

from notion_utils import (
    query_notion_database, 
    update_notion_page, 
    check_script_exists, 
    create_script_report_page,
    reset_all_channels,
    REFERENCE_DB_ID, 
    SCRIPT_DB_ID
)
from youtube_utils import process_channel_url, get_video_transcript, parse_upload_date

logger = logging.getLogger(__name__)

# 글로벌 스케줄러 인스턴스
scheduler = None

async def process_channel(page: Dict[str, Any]) -> bool:
    """특정 채널 페이지를 처리하여 새 스크립트를 생성합니다."""
    try:
        # 페이지 속성 가져오기
        properties = page.get("properties", {})
        page_id = page.get("id")
        
        # 활성화 상태 확인
        is_active = False
        active_property = properties.get("활성화", {})
        if "checkbox" in active_property:
            is_active = active_property["checkbox"]
        
        # 활성화되지 않은 항목은 건너뛰기
        if not is_active:
            logger.info("비활성화된 채널입니다. 스킵합니다.")
            return False
        
        # 제목(키워드) 가져오기
        keyword = ""
        title_property = properties.get("제목", {})
        if "title" in title_property and title_property["title"]:
            keyword = title_property["title"][0]["plain_text"].strip()
        
        # URL 가져오기
        channel_url = ""
        url_property = properties.get("URL", {})
        if "url" in url_property:
            channel_url = url_property["url"]
        
        # 채널명 가져오기
        channel_name = "기타"
        channel_property = properties.get("채널명", {})
        if "select" in channel_property and channel_property["select"]:
            channel_name = channel_property["select"]["name"]
        
        if not channel_url or not keyword:
            logger.warning(f"채널 URL 또는 키워드가 없습니다. 스킵합니다.")
            return False
        
        # 유튜브 채널 URL이 아니면 스킵
        if not "youtube.com/@" in channel_url:
            logger.warning(f"유효한 YouTube 채널 URL이 아닙니다: {channel_url}")
            return False
        
        logger.info(f"Processing channel: {channel_url} with keyword: {keyword}")
        
        # 채널에서 키워드가 포함된 최신 영상 찾기
        latest_video = await process_channel_url(channel_url, keyword)
        
        if not latest_video:
            logger.warning(f"채널에서 키워드가 포함된 영상을 찾을 수 없습니다: {channel_url}")
            return False

        # 라이브 예정(Upcoming) 또는 라이브 중(Live) 영상인 경우 처리하지 않고 활성화 상태 유지
        if latest_video.get("is_upcoming", False) or latest_video.get("is_live", False):
            status = "라이브 예정" if latest_video.get("is_upcoming", False) else "라이브 중"
            logger.info(f"{status} 영상입니다: {latest_video['title']}. 다음에 다시 확인합니다.")
            return False
        
        # 이미 스크립트가 있는지 확인
        if await check_script_exists(latest_video["url"]):
            logger.info(f"이미 스크립트가 존재합니다: {latest_video['title']}")
            
            # 스크립트가 이미 존재하면 활성화 상태를 비활성화로 변경
            await update_notion_page(page_id, {
                "활성화": {"checkbox": False}
            })
            logger.info(f"채널 {channel_name}의 활성화 상태를 비활성화로 변경했습니다.")
            
            return True
        
        # 스크립트 가져오기
        script = await get_video_transcript(latest_video["video_id"])
        
        # 스크립트가 있을 경우만 페이지 생성
        if script and not script.startswith("스크립트를 가져올 수 없습니다"):
            # 영상 날짜 파싱 - 정확한 업로드 날짜로 변환
            upload_date_datetime = parse_upload_date(latest_video.get("upload_date", ""))
            upload_date_iso = upload_date_datetime.isoformat()
            
            # 스크립트 DB에 새 페이지 생성 (속성 설정)
            properties = {
                # 제목은 참고용 DB의 키워드만 사용
                "제목": {
                    "title": [
                        {
                            "text": {
                                "content": keyword
                            }
                        }
                    ]
                },
                # URL 속성 (기존의 원본 영상)
                "URL": {
                    "url": latest_video["url"]
                },
                # 영상 날짜 (추출 시간 대신 영상 업로드 날짜)
                "영상 날짜": {
                    "date": {
                        "start": upload_date_iso
                    }
                },
                # 채널명 속성
                "채널명": {
                    "select": {
                        "name": channel_name
                    }
                },
                # 영상 길이 속성 추가
                "영상 길이": {
                    "rich_text": [
                        {
                            "text": {
                                "content": latest_video.get("video_length", "알 수 없음")
                            }
                        }
                    ]
                },
                # 상태 속성 (분석/완료 두 가지)
                "상태": {
                    "select": {
                        "name": "분석"
                    }
                }
            }
            
            # 디버깅 정보 로깅
            logger.info(f"Creating page for video: {latest_video['title']}")
            logger.info(f"Keyword: {keyword}, Channel: {channel_name}")
            logger.info(f"Upload date: {upload_date_datetime.strftime('%Y-%m-%d')}")
            
            script_page = await create_script_report_page(SCRIPT_DB_ID, properties, script)
            
            if script_page:
                logger.info(f"스크립트+보고서 페이지 생성 완료: {keyword}")
                
                # 스크립트 생성 성공 시 채널 비활성화
                await update_notion_page(page_id, {
                    "활성화": {"checkbox": False}
                })
                logger.info(f"채널 {channel_name}의 활성화 상태를 비활성화로 변경했습니다.")
                
                return True
            else:
                logger.error(f"스크립트+보고서 페이지 생성 실패: {keyword}")
                return False
        else:
            logger.warning(f"스크립트를 가져올 수 없습니다: {latest_video['title']}")
            return False
        
    except Exception as e:
        logger.error(f"채널 처리 중 오류: {str(e)}")
        return False

async def process_channels_by_time(target_hour: int) -> None:
    """특정 시간대에 맞는 채널들을 처리합니다."""
    # 주말인 경우 실행하지 않음
    current_weekday = datetime.now().weekday()
    if current_weekday >= 5:  # 5=토요일, 6=일요일
        logger.info(f"주말({['월','화','수','목','금','토','일'][current_weekday]}요일)에는 스크립트 추출을 실행하지 않습니다.")
        return
    
    logger.info(f"시간대 {target_hour}시에 맞는 채널 처리 시작")
    
    # 참고용 DB의 모든 채널 가져오기
    reference_pages = await query_notion_database(REFERENCE_DB_ID)
    logger.info(f"참고용 DB에서 {len(reference_pages)}개의 채널을 가져왔습니다.")
    
    # 처리할 채널 선택
    channels_to_process = []
    
    for page in reference_pages:
        properties = page.get("properties", {})
        
        # 활성화 상태 확인
        is_active = False
        active_property = properties.get("활성화", {})
        if "checkbox" in active_property:
            is_active = active_property["checkbox"]
        
        if not is_active:
            continue
        
        # 시간 속성 가져오기
        upload_time = None
        time_property = properties.get("시간", {})
        if "number" in time_property and time_property["number"] is not None:
            upload_time = int(time_property["number"])
        
        if upload_time is None:
            logger.warning(f"채널의 시간 속성이 없습니다. 기본값 9시로 설정합니다.")
            upload_time = 9
        
        # 시간대별 스크립트 추출 시도 시간 설정 및 체크
        should_process = False
        
        if upload_time < 12:  # 오전 영상
            if target_hour in [9, 10, 11]:
                should_process = True
        elif upload_time < 20:  # 오후 영상
            if target_hour in [upload_time + 2, upload_time + 3, upload_time + 4]:
                should_process = True
        else:  # 늦은 저녁 영상
            if target_hour in [22, 23, 0, 1, 2, 3]:
                should_process = True
        
        if should_process:
            channels_to_process.append(page)
    
    logger.info(f"{target_hour}시에 처리할 채널 {len(channels_to_process)}개를 찾았습니다.")
    
    # 채널 처리
    success_count = 0
    
    for channel_page in channels_to_process:
        success = await process_channel(channel_page)
        if success:
            success_count += 1
    
    logger.info(f"{target_hour}시 처리 완료: {success_count}/{len(channels_to_process)} 채널 성공")

async def reset_channels_daily() -> None:
    """매일 새벽 4시에 모든 채널을 활성화 상태로 초기화합니다."""
    logger.info("모든 채널 활성화 작업 시작")
    success = await reset_all_channels()
    
    if success:
        logger.info("모든 채널이 성공적으로 활성화되었습니다.")
    else:
        logger.error("일부 또는 모든 채널의 활성화에 실패했습니다.")

def setup_scheduler() -> AsyncIOScheduler:
    """스케줄러를 설정하고 작업을 예약합니다."""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
    
    scheduler = AsyncIOScheduler()
    
    # 새벽 4시에 모든 채널 초기화
    scheduler.add_job(
        reset_channels_daily,
        CronTrigger(hour=4, minute=0),
        id="reset_channels_daily",
        replace_existing=True
    )
    
    # 주요 시간대별 작업 추가 (0-23시)
    for hour in range(24):
        scheduler.add_job(
            process_channels_by_time,
            CronTrigger(hour=hour, minute=0),
            args=[hour],
            id=f"process_channels_{hour}",
            replace_existing=True
        )
    
    # 스케줄러 시작
    scheduler.start()
    logger.info("Scheduler has been set up and is running.")
    
    return scheduler

async def simulate_scheduler_at_time(hour: int, minute: int, weekday: int, simulate_only: bool = True) -> Dict[str, Any]:
    """특정 시간과 요일에 어떤 작업이 실행될지 시뮬레이션합니다."""
    # 주말인 경우
    if weekday >= 5:  # 5=토요일, 6=일요일
        return {"message": "주말에는 작업이 실행되지 않습니다.", "tasks": []}
    
    # 현재 시각에 해당하는 작업 찾기
    tasks = []
    
    # 모든 채널 초기화 (새벽 4시)
    if hour == 4 and minute == 0:
        tasks.append({
            "name": "모든 채널 활성화",
            "action": "reset_all_channels"
        })
        
        if not simulate_only:
            logger.info("실제 모든 채널 활성화 실행")
            await reset_all_channels()
    
    # 참고용 DB의 모든 채널 조회
    reference_pages = await query_notion_database(REFERENCE_DB_ID)
    logger.info(f"테스트: {len(reference_pages)}개의 채널을 가져왔습니다.")
    
    for page in reference_pages:
        properties = page.get("properties", {})
        
        # 활성화 상태 확인
        is_active = False
        active_property = properties.get("활성화", {})
        if "checkbox" in active_property:
            is_active = active_property["checkbox"]
        
        if not is_active:
            continue
        
        # 시간 속성 가져오기
        upload_time = 9  # 기본값
        time_property = properties.get("시간", {})
        if "number" in time_property and time_property["number"] is not None:
            upload_time = int(time_property["number"])
        
        # 채널명과 키워드 가져오기
        channel_name = "기타"
        if "채널명" in properties and "select" in properties["채널명"] and properties["채널명"]["select"]:
            channel_name = properties["채널명"]["select"]["name"]
        
        keyword = ""
        if "제목" in properties and "title" in properties["제목"] and properties["제목"]["title"]:
            keyword = properties["제목"]["title"][0]["plain_text"].strip()
        
        # 시간대별 스크립트 추출 시도 시간 설정
        extraction_times = []
        
        if upload_time < 12:  # 오전 영상
            extraction_times = [9, 10, 11]
        elif upload_time < 20:  # 오후 영상
            extraction_times = [upload_time + 2, upload_time + 3, upload_time + 4]
        else:  # 늦은 저녁 영상
            extraction_times = [22, 23, 0, 1, 2, 3]
        
        # 현재 시각에 맞는 작업 확인
        if hour in extraction_times:
            tasks.append({
                "name": f"스크립트 추출 시도",
                "channel": channel_name,
                "keyword": keyword,
                "upload_time": upload_time,
                "scheduled_time": hour
            })
            
            if not simulate_only:
                # 실제 스크립트 추출 실행
                logger.info(f"실제 채널 처리 실행: {channel_name} ({keyword})")
                success = await process_channel(page)
                if success:
                    logger.info(f"채널 처리 성공: {channel_name}")
                else:
                    logger.warning(f"채널 처리 실패: {channel_name}")
    
    return {
        "simulated_time": f"{hour:02d}:{minute:02d}",
        "weekday": ["월", "화", "수", "목", "금", "토", "일"][weekday],
        "tasks": tasks
    }