"""
데이터 제공자 모듈 - 다양한 자산 유형(주식, 암호화폐, 원자재)의 가격 데이터를 제공합니다.
yfinance를 기본 데이터 소스로 사용합니다.
"""

import asyncio
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# 로깅 설정
logger = logging.getLogger(__name__)

# Series 또는 DataFrame에서 안전하게 스칼라 값을 추출하는 헬퍼 함수
def safe_scalar(obj):
    """
    pandas Series나 numpy 배열에서 안전하게 스칼라 값을 추출합니다.
    이미 스칼라 값이면 그대로 반환합니다.
    """
    if isinstance(obj, pd.Series):
        return obj.iloc[0]  # Series에서 첫 번째 값을 추출
    elif isinstance(obj, pd.DataFrame):
        return obj.iloc[0, 0]  # DataFrame에서 첫 번째 셀 값을 추출
    else:
        return obj  # 이미 스칼라 값이면 그대로 반환

class DataProvider:
    """다양한 자산 유형의 가격 데이터를 제공하는 클래스"""
    
    @staticmethod
    async def get_data(
        symbol: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None,
        asset_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        지정된 심볼(티커)에 대한 가격 데이터를 가져옵니다.
        
        Args:
            symbol: 자산 심볼(티커)
            start_date: 시작일(YYYY-MM-DD)
            end_date: 종료일(YYYY-MM-DD)
            asset_type: 자산 유형 (명시적으로 지정할 경우)
            
        Returns:
            데이터 조회 결과 딕셔너리
        """
        try:
            # 기본 날짜 설정
            if end_date is None:
                end_date = datetime.now().strftime("%Y-%m-%d")
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            logger.info(f"데이터 조회: {symbol} ({start_date} ~ {end_date}, 유형: {asset_type if asset_type else '자동 감지'})")
            
            # 한국 주식인 경우 심볼 처리
            processed_symbol = symbol
            if asset_type == "stock" and len(symbol) == 6 and symbol.isdigit():
                if not (symbol.endswith('.KS') or symbol.endswith('.KQ')):
                    processed_symbol = f"{symbol}.KS"  # 기본적으로 KOSPI로 가정
            
            # 새로운 방식: yfinance.download 사용
            data = await DataProvider._fetch_yfinance_data(processed_symbol, start_date, end_date)
            
            if data.empty:
                return {"status": "error", "error": f"자산 {symbol}의 데이터를 찾을 수 없습니다."}
            
            # 자산명 가져오기
            asset_name = await DataProvider._get_asset_name(processed_symbol, asset_type)
            
            # 기본 정보 추출 (스칼라 값 안전하게 추출)
            first_close = safe_scalar(data.iloc[0]["Close"])
            last_close = safe_scalar(data.iloc[-1]["Close"])
            price_change = ((last_close - first_close) / first_close) * 100
            
            info = {
                "symbol": symbol,
                "name": asset_name,
                "asset_type": asset_type or "unknown",
                "current_price": round(last_close, 2),
                "start_price": round(first_close, 2),
                "price_change": round(price_change, 2),
                "start_date": data.index[0].strftime("%Y-%m-%d"),
                "end_date": data.index[-1].strftime("%Y-%m-%d"),
                "data_points": len(data)
            }
            
            return {
                "status": "success",
                "data": info,
                "dataframe": data
            }
        except Exception as e:
            logger.error(f"데이터 조회 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())  # 스택 트레이스 추가
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    async def _fetch_yfinance_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        yfinance에서 비동기적으로 가격 데이터를 가져옵니다.
        
        Args:
            symbol: 자산 심볼
            start_date: 시작일
            end_date: 종료일
            
        Returns:
            가격 데이터가 포함된 DataFrame
        """
        try:
            # 새로운 방식: yf.download 사용 (비동기로 처리)
            data = await asyncio.to_thread(
                yf.download, 
                symbol, 
                start=start_date, 
                end=end_date,
                progress=False,
                auto_adjust=True  # 수정주가 사용
            )
            
            # 결과 데이터프레임에 필요한 칼럼이 있는지 확인
            if data.empty or 'Close' not in data.columns:
                logger.warning(f"심볼 {symbol}에 대한 데이터를 가져올 수 없습니다.")
                return pd.DataFrame()
            
            return data
        except Exception as e:
            logger.error(f"yfinance 데이터 조회 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())  # 스택 트레이스 추가
            return pd.DataFrame()
    
    @staticmethod
    async def _get_asset_name(symbol: str, asset_type: Optional[str] = None) -> str:
        """
        자산의 이름을 가져옵니다.
        
        Args:
            symbol: 자산 심볼
            asset_type: 자산 유형
            
        Returns:
            자산 이름
        """
        try:
            # 티커 객체 생성
            ticker = yf.Ticker(symbol)
            
            # 비동기적으로 티커 정보 가져오기
            info = await asyncio.to_thread(lambda: ticker.info)
            
            # 자산명 반환
            if 'shortName' in info and info['shortName']:
                return info['shortName']
            elif 'longName' in info and info['longName']:
                return info['longName']
            else:
                # 자산 유형에 따라 기본 이름 제공
                if asset_type == "stock":
                    if symbol.endswith('.KS'):
                        base_symbol = symbol.replace('.KS', '')
                        return f"{base_symbol} (KOSPI)"
                    elif symbol.endswith('.KQ'):
                        base_symbol = symbol.replace('.KQ', '')
                        return f"{base_symbol} (KOSDAQ)"
                return symbol
        except Exception as e:
            logger.debug(f"자산명 조회 실패: {str(e)}")
            return symbol