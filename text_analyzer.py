"""
텍스트 분석 모듈 - Gemini API를 활용해 사용자 요청에서 백테스팅 매개변수를 추출합니다.
"""

import os
import json
import logging
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from google import generativeai as genai

# 로깅 설정
logger = logging.getLogger(__name__)

class TextAnalyzer:
    """LLM을 활용한 텍스트 분석 클래스 - 백테스팅 매개변수 추출"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        텍스트 분석기 초기화
        
        Args:
            api_key: Gemini API 키 (None인 경우 환경 변수에서 가져옴)
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다")
            
        # API 키 설정
        genai.configure(api_key=self.api_key)
        
        # 모델 설정 - 원래 코드와 동일하게 맞춤
        self.model = "gemini-2.5-flash-preview-04-17"
    
    async def analyze_backtest_request(self, text: str) -> Dict[str, Any]:
        """
        사용자 요청에서 백테스팅 매개변수를 추출합니다.
        
        Args:
            text: 사용자 요청 텍스트 (예: "금을 6개월 전에 100만원어치 샀다면 지금 얼마가 되었을까?")
            
        Returns:
            분석 결과 딕셔너리
        """
        try:
            # LLM에 분석 요청
            response_text = await self._query_gemini(text)
            
            # 응답 처리
            logger.info(f"LLM 응답: {response_text}")
            
            # JSON 파싱 시도
            try:
                # JSON 문자열 추출 (텍스트 내 JSON 객체 찾기)
                if '{' in response_text and '}' in response_text:
                    # ```json으로 시작하는 마크다운 코드 블록 처리
                    if "```json" in response_text:
                        # 코드 블록 추출
                        json_str = response_text.split("```json")[1].split("```")[0].strip()
                    else:
                        # 일반 JSON 추출
                        json_str = response_text[response_text.find('{'):response_text.rfind('}')+1]
                    
                    params = json.loads(json_str)
                    
                    # 티커 심볼 검사 및 변환
                    if 'symbol' in params:
                        # 이미 종목코드 형식이면 그대로 사용
                        if params['symbol'].isdigit() and len(params['symbol']) == 6:
                            pass
                        # ETF, 미국 주식 등의 티커 심볼 처리
                        elif params['asset_type'] in ['etf', 'stock'] and not params['symbol'].isdigit():
                            # 여기서 티커 심볼이 적절한지 확인하는 로직 추가 가능
                            # 예: 미국 주식/ETF 티커 유효성 검사
                            pass
                    
                    return {
                        "status": "success",
                        "request": text,
                        "params": params
                    }
                else:
                    logger.warning("LLM 응답에서 JSON을 찾을 수 없음")
                    return {
                        "status": "error",
                        "error": "LLM 응답에서 유효한 JSON을 찾을 수 없습니다",
                        "request": text,
                        "response": response_text
                    }
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 오류: {str(e)}, 응답: {response_text}")
                return {
                    "status": "error",
                    "error": f"JSON 파싱 오류: {str(e)}",
                    "request": text,
                    "response": response_text
                }
        except Exception as e:
            logger.error(f"텍스트 분석 중 오류 발생: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "request": text
            }
    
    async def _query_gemini(self, prompt: str) -> str:
        """
        Gemini API에 백테스팅 매개변수 추출 쿼리를 보냅니다.
        
        Args:
            prompt: 사용자 프롬프트
            
        Returns:
            Gemini 응답 텍스트
        """
        try:
            # 현재 날짜 정보 제공
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # 시스템 지시사항
            system_instruction = f"""
            당신은 백테스팅 매개변수 추출 전문가입니다. 사용자의 자연어 요청에서 자산 정보, 기간, 투자 금액을 정확히 추출해야 합니다.
            
            오늘의 날짜는 {current_date}입니다. 상대적인 날짜 계산 시 이 날짜를 기준으로 합니다.
            
            다음 형식의 JSON으로 응답하세요:
            {{
            "asset_type": "자산 유형(stock/crypto/commodity/etf 중 하나)",
            "symbol": "자산 심볼/코드",
            "start_date": "YYYY-MM-DD 형식의 시작일",
            "end_date": "YYYY-MM-DD 형식의 종료일(기본값: 현재)",
            "investment_amount": 투자 금액(숫자, 단위: 원)
            }}
            
            자산 유형별 심볼 형식:
            1. 한국 주식:
            - 코스피 종목: 6자리 숫자 + .KS (예: 삼성전자는 "005930.KS")
            - 코스닥 종목: 6자리 숫자 + .KQ (예: 셀트리온제약은 "068760.KQ")
            2. 암호화폐: 티커-USD (예: 비트코인은 "BTC-USD")
            3. 원자재: 표준 심볼 (예: 금은 "GC=F", 원유는 "CL=F")
            4. 미국 주식/ETF: 티커 심볼 (예: 애플은 "AAPL", QQQ는 "QQQ")
            
            기간은 절대 날짜나 상대 표현(예: "6개월 전")을 YYYY-MM-DD 형식으로 변환하세요.
            투자 금액은 숫자로만 표현하세요(단위 없이, 예: 100만원 -> 1000000).
            
            자산을 정확하게 식별할 수 없으면, 가장 가능성 높은 추측을 해주세요:
            - "주식" → 삼성전자(005930.KS)
            - "금" → 금 선물(GC=F)
            - "코인" → 비트코인(BTC-USD)
            
            오직 JSON만 응답하고 다른 설명은 포함하지 마세요.
            """.strip()
            
            user_prompt = f"다음 요청에서 백테스팅 매개변수를 추출해주세요: {prompt}"
            
            # 모델 생성
            model = genai.GenerativeModel(self.model)
            
            # 구글 검색 활성화 설정
            generation_config = {
                "temperature": 0.1,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 1024
            }
            
            # 프롬프트 구성
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
            
            # API 호출
            response = await asyncio.to_thread(
                model.generate_content,
                contents=[system_instruction, user_prompt],
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # 응답 텍스트 추출
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'parts') and len(response.parts) > 0:
                return response.parts[0].text
            else:
                logger.warning("Gemini API가 빈 응답을 반환했습니다.")
                return "{}"
                
        except Exception as e:
            logger.error(f"Gemini API 호출 중 오류: {str(e)}")
            return "{}"