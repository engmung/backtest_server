"""
주식, 암호화폐, 원자재 백테스팅 API 서비스
- 자연어 입력을 통한 백테스팅 분석
- 다양한 자산 유형(주식, 암호화폐, 원자재) 지원
- yfinance 기반 데이터 소스
- LLM(Gemini) 활용 텍스트 분석
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from text_analyzer import TextAnalyzer
from backtest import BacktestAnalyzer

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI 앱 설정
app = FastAPI(title="종합 자산 백테스팅 API")

# CORS 설정 업데이트 (main.py 파일)
app.add_middleware(
    CORSMiddleware,
    # 여러 출처를 배열로 지정하여 모두 허용
    allow_origins=[
        "https://backtestai-two.vercel.app",  # Vercel 프로덕션 사이트
        "https://backtest.ai.kr",
        "http://localhost:3000",              # React 개발 서버 (CRA)
        "http://localhost:5173",              # Vite 개발 서버
        "http://127.0.0.1:3000",              # 로컬 개발 대체 URL
        "http://127.0.0.1:5173"               # 로컬 개발 대체 URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 자연어 백테스팅 요청 모델
class NaturalBacktestRequest(BaseModel):
    prompt: str

# API 엔드포인트
@app.get("/")
async def root():
    return {"message": "종합 자산 백테스팅 API", "version": "1.0.0"}

@app.post("/natural-backtest")
async def natural_backtest(request: NaturalBacktestRequest):
    """
    자연어 프롬프트로 백테스팅을 요청합니다.
    
    예:
    - "삼성전자를 3개월 전에 100만원어치 샀다면 지금 얼마가 되었을까?"
    - "금을 1년 전에 투자했다면 수익이 얼마나 났을까요?"
    - "비트코인 6개월 전 500만원 투자 성과는?"
    """
    try:
        user_prompt = request.prompt
        logger.info(f"자연어 백테스팅 요청: '{user_prompt}'")
        
        # 텍스트 분석기 초기화
        text_analyzer = TextAnalyzer()
        
        # LLM으로 매개변수 추출
        analysis_result = await text_analyzer.analyze_backtest_request(user_prompt)
        
        if analysis_result["status"] != "success":
            return {
                "status": "error", 
                "message": "요청 분석 중 오류가 발생했습니다", 
                "details": analysis_result.get("error", "알 수 없는 오류")
            }
        
        # 추출된 매개변수
        params = analysis_result["params"]
        logger.info(f"추출된 매개변수: {params}")
        
        # 필수 매개변수 확인
        required_params = ["symbol", "asset_type", "start_date"]
        missing_params = [param for param in required_params if param not in params]
        
        if missing_params:
            return {
                "status": "error",
                "message": f"필수 매개변수가 누락되었습니다: {', '.join(missing_params)}",
                "params": params
            }
        
        # 백테스팅 전 심볼 처리
        symbol = params["symbol"]
        asset_type = params["asset_type"]
        
        # 투자 금액 설정 (LLM 분석 결과에서 가져옴)
        investment_amount = params.get("investment_amount", 1000000)  # 기본값: 100만원
        
        # 종료일 설정 (기본값: 현재)
        end_date = params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
        
        # 백테스팅 수행
        backtest_result = await BacktestAnalyzer.backtest_asset(
            symbol=symbol,
            start_date=params["start_date"],
            end_date=end_date,
            investment_amount=investment_amount,
            asset_type=asset_type
        )
        
        # 콘솔에 결과 출력 (로깅용)
        if backtest_result["status"] == "success":
            BacktestAnalyzer.print_backtest_result(backtest_result)
        
        # 응답 생성
        return {
            "status": "success" if backtest_result["status"] == "success" else "error",
            "request": user_prompt,
            "parameters": params,
            "result": backtest_result
        }
    
    except Exception as e:
        logger.error(f"백테스팅 처리 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"백테스팅 처리 중 오류가 발생했습니다: {str(e)}")

@app.post("/backtest")
async def backtest_asset(
    symbol: str = Query(..., description="자산 심볼/코드"),
    start_date: str = Query(..., description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(None, description="종료일 (YYYY-MM-DD)"),
    investment_amount: float = Query(1000000, description="투자 금액 (원)"),
    asset_type: str = Query(None, description="자산 유형 (stock/crypto/commodity/etf)")
):
    """
    지정된 자산에 대한 백테스팅을 수행합니다.
    """
    try:
        logger.info(f"백테스팅 요청: {symbol} ({start_date} ~ {end_date})")
        
        # 종료일 기본값 설정 (현재)
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        # 백테스팅 수행
        result = await BacktestAnalyzer.backtest_asset(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            investment_amount=investment_amount,
            asset_type=asset_type
        )
        
        return result
    
    except Exception as e:
        logger.error(f"백테스팅 처리 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"백테스팅 처리 중 오류가 발생했습니다: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    logger.info("종합 자산 백테스팅 API 시작")
    logger.info("예시 요청: curl -X POST http://localhost:8001/natural-backtest -H 'Content-Type: application/json' -d '{\"prompt\": \"삼성전자를 3개월 전에 100만원어치 샀다면 지금 얼마가 되었을까?\"}'")
    logger.info("예시 요청: curl -X POST http://localhost:8001/natural-backtest -H 'Content-Type: application/json' -d '{\"prompt\": \"금을 1년 전에 투자했다면 수익이 얼마나 났을까요?\"}'")
    logger.info("예시 요청: curl -X POST http://localhost:8001/natural-backtest -H 'Content-Type: application/json' -d '{\"prompt\": \"비트코인 6개월 전 500만원 투자 성과는?\"}'")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)