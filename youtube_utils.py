import re
import json
import logging
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from youtube_transcript_api import YouTubeTranscriptApi
import asyncio

logger = logging.getLogger(__name__)

def extract_initial_data(html_content: str) -> dict:
    """YouTube의 초기 데이터를 추출합니다."""
    try:
        # ytInitialData가 포함된 script 태그를 찾기
        pattern = re.compile(r'var\s+ytInitialData\s*=\s*(\{.+?\});</script>', re.DOTALL)
        match = pattern.search(html_content)
        
        if not match:
            # 다른 패턴 시도
            pattern = re.compile(r'window\["ytInitialData"\]\s*=\s*(\{.+?\});', re.DOTALL)
            match = pattern.search(html_content)
        
        if not match:
            # 또 다른 패턴 시도
            pattern = re.compile(r'ytInitialData\s*=\s*(\{.+?\});', re.DOTALL)
            match = pattern.search(html_content)
        
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            return data
        else:
            logger.warning("ytInitialData를 찾을 수 없습니다.")
            return {}
    except Exception as e:
        logger.error(f"초기 데이터 추출 오류: {str(e)}")
        return {}

def parse_upload_date(upload_time_text: str) -> datetime:
    """
    YouTube 업로드 시간 텍스트를 실제 날짜로 변환합니다.
    예: "3일 전", "5시간 전" 등을 실제 날짜로 변환
    """
    now = datetime.now()
    
    if not upload_time_text:
        return now
    
    try:
        # 숫자 추출
        number_match = re.search(r'(\d+)', upload_time_text)
        if not number_match:
            return now
        
        value = int(number_match.group(1))
        
        # 시간 단위에 따른 계산
        if "분 전" in upload_time_text or "minutes ago" in upload_time_text:
            return now - timedelta(minutes=value)
        elif "시간 전" in upload_time_text or "hours ago" in upload_time_text:
            return now - timedelta(hours=value)
        elif "일 전" in upload_time_text or "days ago" in upload_time_text:
            return now - timedelta(days=value)
        elif "주 전" in upload_time_text or "weeks ago" in upload_time_text:
            return now - timedelta(weeks=value)
        elif "개월 전" in upload_time_text or "months ago" in upload_time_text:
            return now - timedelta(days=value*30)
        elif "년 전" in upload_time_text or "years ago" in upload_time_text:
            return now - timedelta(days=value*365)
        else:
            # 직접적인 날짜 형식 처리 (예: "2024년 3월 13일")
            date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', upload_time_text)
            if date_match:
                year, month, day = map(int, date_match.groups())
                return datetime(year, month, day)
            
            # 영어 날짜 형식 처리 (예: "Mar 13, 2024")
            eng_date_match = re.search(r'([A-Za-z]{3})\s*(\d{1,2}),?\s*(\d{4})', upload_time_text)
            if eng_date_match:
                month_str, day, year = eng_date_match.groups()
                month_dict = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month = month_dict.get(month_str, 1)
                return datetime(int(year), month, int(day))
    except Exception as e:
        logger.error(f"날짜 파싱 오류: {str(e)}")
    
    return now

def find_videos_with_keyword(data: dict, keyword: str) -> List[Dict[str, Any]]:
    """Extract video information with the given keyword from YouTube initial data."""
    videos = []
    
    try:
        # Search possible paths
        tab_renderers = None
        
        # Find tab renderer
        if "contents" in data:
            if "twoColumnBrowseResultsRenderer" in data["contents"]:
                if "tabs" in data["contents"]["twoColumnBrowseResultsRenderer"]:
                    tab_renderers = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
            elif "sectionListRenderer" in data["contents"]:
                if "contents" in data["contents"]["sectionListRenderer"]:
                    tab_renderers = [{"tabRenderer": {"content": data["contents"]["sectionListRenderer"]}}]
        
        if not tab_renderers:
            logger.warning("Could not find tab renderers.")
            return videos
        
        # Examine each tab
        for tab in tab_renderers:
            if "tabRenderer" not in tab:
                continue
            
            # Extract content
            content = tab["tabRenderer"].get("content", {})
            
            # Section list renderer
            if "sectionListRenderer" in content:
                for section in content["sectionListRenderer"].get("contents", []):
                    # Item section renderer
                    if "itemSectionRenderer" in section:
                        for content_item in section["itemSectionRenderer"].get("contents", []):
                            # Grid renderer
                            if "gridRenderer" in content_item:
                                for item in content_item["gridRenderer"].get("items", []):
                                    # Extract video info (grid format)
                                    if "gridVideoRenderer" in item:
                                        video_renderer = item["gridVideoRenderer"]
                                        
                                        # Extract title
                                        title = ""
                                        if "title" in video_renderer and "runs" in video_renderer["title"]:
                                            for run in video_renderer["title"]["runs"]:
                                                title += run.get("text", "")
                                        
                                        # Check keyword
                                        if keyword.lower() in title.lower():
                                            # Extract video ID
                                            video_id = video_renderer.get("videoId", "")
                                            
                                            # Create URL
                                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                                            
                                            # Extract upload time
                                            upload_time = ""
                                            if "publishedTimeText" in video_renderer:
                                                upload_time = video_renderer["publishedTimeText"].get("simpleText", "")
                                            
                                            # Check live info
                                            is_upcoming = False
                                            is_live = False
                                            
                                            if "thumbnailOverlays" in video_renderer:
                                                for overlay in video_renderer["thumbnailOverlays"]:
                                                    if "thumbnailOverlayTimeStatusRenderer" in overlay:
                                                        status_renderer = overlay["thumbnailOverlayTimeStatusRenderer"]
                                                        if "style" in status_renderer:
                                                            if status_renderer["style"] == "UPCOMING":
                                                                is_upcoming = True
                                                            elif status_renderer["style"] == "LIVE":
                                                                is_live = True
                                            
                                            # Extract video length
                                            video_length = "Unknown"
                                            if "lengthText" in video_renderer:
                                                if "simpleText" in video_renderer["lengthText"]:
                                                    video_length = video_renderer["lengthText"]["simpleText"]
                                            
                                            videos.append({
                                                "title": title,
                                                "url": video_url,
                                                "video_id": video_id,
                                                "upload_date": upload_time,
                                                "is_upcoming": is_upcoming,
                                                "is_live": is_live,
                                                "video_length": video_length
                                            })
                                            logger.info(f"Found matching video: {title} {'(Upcoming)' if is_upcoming else '(Live)' if is_live else ''}")
                            
                            # Regular video info extraction (list format)
                            elif "videoRenderer" in content_item:
                                video_renderer = content_item["videoRenderer"]
                                
                                # Extract title
                                title = ""
                                if "title" in video_renderer and "runs" in video_renderer["title"]:
                                    for run in video_renderer["title"]["runs"]:
                                        title += run.get("text", "")
                                
                                # Check keyword
                                if keyword.lower() in title.lower():
                                    # Extract video ID
                                    video_id = video_renderer.get("videoId", "")
                                    
                                    # Create URL
                                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                                    
                                    # Extract upload time
                                    upload_time = ""
                                    if "publishedTimeText" in video_renderer:
                                        upload_time = video_renderer["publishedTimeText"].get("simpleText", "")
                                    
                                    # Check live info
                                    is_upcoming = False
                                    is_live = False
                                    
                                    if "badges" in video_renderer:
                                        for badge in video_renderer["badges"]:
                                            if "metadataBadgeRenderer" in badge:
                                                badge_renderer = badge["metadataBadgeRenderer"]
                                                if "style" in badge_renderer and badge_renderer.get("style") == "BADGE_STYLE_TYPE_LIVE_NOW":
                                                    is_live = True
                                    
                                    if "thumbnailOverlays" in video_renderer:
                                        for overlay in video_renderer["thumbnailOverlays"]:
                                            if "thumbnailOverlayTimeStatusRenderer" in overlay:
                                                status_renderer = overlay["thumbnailOverlayTimeStatusRenderer"]
                                                if "style" in status_renderer:
                                                    if status_renderer["style"] == "UPCOMING":
                                                        is_upcoming = True
                                                    elif status_renderer["style"] == "LIVE":
                                                        is_live = True
                                    
                                    # Extract video length
                                    video_length = "Unknown"
                                    if "lengthText" in video_renderer:
                                        if "simpleText" in video_renderer["lengthText"]:
                                            video_length = video_renderer["lengthText"]["simpleText"]
                                    
                                    videos.append({
                                        "title": title,
                                        "url": video_url,
                                        "video_id": video_id,
                                        "upload_date": upload_time,
                                        "is_upcoming": is_upcoming,
                                        "is_live": is_live,
                                        "video_length": video_length
                                    })
                                    logger.info(f"Found matching video: {title} {'(Upcoming)' if is_upcoming else '(Live)' if is_live else ''}")
            
            # Rich grid renderer
            elif "richGridRenderer" in content:
                for item in content["richGridRenderer"].get("contents", []):
                    if "richItemRenderer" in item:
                        if "content" in item["richItemRenderer"]:
                            content_item = item["richItemRenderer"]["content"]
                            
                            # Extract video info
                            if "videoRenderer" in content_item:
                                video_renderer = content_item["videoRenderer"]
                                
                                # Extract title
                                title = ""
                                if "title" in video_renderer and "runs" in video_renderer["title"]:
                                    for run in video_renderer["title"]["runs"]:
                                        title += run.get("text", "")
                                
                                # Check keyword
                                if keyword.lower() in title.lower():
                                    # Extract video ID
                                    video_id = video_renderer.get("videoId", "")
                                    
                                    # Create URL
                                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                                    
                                    # Extract upload time
                                    upload_time = ""
                                    if "publishedTimeText" in video_renderer:
                                        upload_time = video_renderer["publishedTimeText"].get("simpleText", "")
                                    
                                    # Check live info
                                    is_upcoming = False
                                    is_live = False
                                    
                                    if "badges" in video_renderer:
                                        for badge in video_renderer["badges"]:
                                            if "metadataBadgeRenderer" in badge:
                                                badge_renderer = badge["metadataBadgeRenderer"]
                                                if "style" in badge_renderer and badge_renderer.get("style") == "BADGE_STYLE_TYPE_LIVE_NOW":
                                                    is_live = True
                                    
                                    if "thumbnailOverlays" in video_renderer:
                                        for overlay in video_renderer["thumbnailOverlays"]:
                                            if "thumbnailOverlayTimeStatusRenderer" in overlay:
                                                status_renderer = overlay["thumbnailOverlayTimeStatusRenderer"]
                                                if "style" in status_renderer:
                                                    if status_renderer["style"] == "UPCOMING":
                                                        is_upcoming = True
                                                    elif status_renderer["style"] == "LIVE":
                                                        is_live = True
                                    
                                    # Extract video length
                                    video_length = "Unknown"
                                    if "lengthText" in video_renderer:
                                        if "simpleText" in video_renderer["lengthText"]:
                                            video_length = video_renderer["lengthText"]["simpleText"]
                                    
                                    videos.append({
                                        "title": title,
                                        "url": video_url,
                                        "video_id": video_id,
                                        "upload_date": upload_time,
                                        "is_upcoming": is_upcoming,
                                        "is_live": is_live,
                                        "video_length": video_length
                                    })
                                    logger.info(f"Found matching video: {title} {'(Upcoming)' if is_upcoming else '(Live)' if is_live else ''}")
        
        # Sort videos (Live > Regular videos > Upcoming)
        videos.sort(key=lambda v: (
            -1 if v.get("is_live", False) else (1 if v.get("is_upcoming", False) else 0)
        ))
        
        return videos
    except Exception as e:
        logger.error(f"Error extracting video info: {str(e)}")
        return videos

async def process_channel_url(channel_url: str, keyword: str, max_retries: int = 3, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """채널 URL에서 키워드가 포함된 최신 영상을 찾습니다."""
    logger.info(f"Processing channel URL: {channel_url} with keyword: {keyword}")
    
    # channel URL에서 streams 경로가 없으면 추가
    if not channel_url.endswith("/streams") and not channel_url.endswith("/videos"):
        channel_url = f"{channel_url}/streams"
    
    # 채널 페이지 HTML 가져오기
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    # 재시도 로직
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                logger.info(f"Fetching channel page (attempt {attempt+1}/{max_retries})")
                response = await client.get(
                    channel_url, 
                    headers=headers, 
                    follow_redirects=True, 
                    timeout=timeout
                )
                response.raise_for_status()
                
                # YouTube의 초기 데이터 추출
                data = extract_initial_data(response.text)
                
                if not data:
                    logger.warning("YouTube 데이터를 추출할 수 없습니다")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        return None
                
                # 키워드가 포함된 비디오 찾기
                videos = find_videos_with_keyword(data, keyword)
                
                if not videos:
                    logger.warning(f"키워드 '{keyword}'가 포함된 영상을 찾을 수 없습니다: {channel_url}")
                    return None
                
                # 일반 영상만 필터링 (라이브 중, 라이브 예정 제외)
                normal_videos = [v for v in videos if not v.get("is_live", False) and not v.get("is_upcoming", False)]
                
                if not normal_videos:
                    logger.warning(f"키워드 '{keyword}'가 포함된 일반 영상을 찾을 수 없습니다. 라이브 또는 라이브 예정 영상만 있습니다.")
                    return None
                
                # 가장 최근 일반 영상 선택
                latest_video = normal_videos[0]
                logger.info(f"Found regular video: {latest_video['title']}")
                return latest_video
                
        except httpx.TimeoutException:
            logger.warning(f"Timeout when fetching channel page (attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(f"Max retries reached when fetching channel: {channel_url}")
                return None
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error processing channel: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return None
    
    return None

async def get_video_transcript(video_id: str, max_retries: int = 3) -> str:
    """비디오 ID로부터 자막을 가져옵니다."""
    logger.info(f"Getting transcript for video ID: {video_id}")
    
    for attempt in range(max_retries):
        try:
            # 한국어 자막 시도
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["ko"])
            logger.info(f"Found Korean transcript with {len(transcript_list)} entries")
            return " ".join([entry["text"] for entry in transcript_list])
        except Exception as e:
            logger.warning(f"Korean transcript error (attempt {attempt+1}/{max_retries}): {str(e)}")
            
            try:
                # 자동 언어 감지 시도
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                logger.info(f"Found transcript with auto-detected language")
                return " ".join([entry["text"] for entry in transcript_list])
            except Exception as e2:
                logger.error(f"Auto-detect transcript error (attempt {attempt+1}/{max_retries}): {str(e2)}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return f"스크립트를 가져올 수 없습니다: {str(e2)}"
    
    return "스크립트를 가져올 수 없습니다: 최대 재시도 횟수 초과"