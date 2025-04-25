"""
백테스팅 모듈 - 다양한 자산 유형에 대한 백테스팅 및 포트폴리오 분석 기능을 제공합니다.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from data_provider import DataProvider

# 로깅 설정
logger = logging.getLogger(__name__)

# NumPy 데이터 타입을 Python 기본 타입으로 변환하는 함수
def convert_numpy_types(obj):
    """NumPy 데이터 타입을 Python 기본 타입으로 변환합니다."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    return obj

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

class BacktestAnalyzer:
    """다양한 자산 유형에 대한 백테스팅 및 포트폴리오 분석 기능을 제공하는 클래스"""
    
    @staticmethod
    async def backtest_asset(
        symbol: str, 
        start_date: str, 
        end_date: str, 
        investment_amount: float = 1000000,
        asset_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        단일 자산에 대한 백테스팅을 수행합니다.
        
        Args:
            symbol: 자산 심볼
            start_date: 시작일(YYYY-MM-DD)
            end_date: 종료일(YYYY-MM-DD)
            investment_amount: 투자 금액 (기본값: 100만원)
            asset_type: 자산 유형 (명시적으로 지정할 경우)
            
        Returns:
            백테스팅 결과 딕셔너리
        """
        try:
            logger.info(f"백테스팅 데이터 요청: {symbol} ({start_date} ~ {end_date})")
            
            # 심볼 전처리
            processed_symbol = symbol
            
            # 자산 종류에 따른 처리
            if asset_type == "stock" and len(symbol) == 6 and symbol.isdigit():
                if not (symbol.endswith('.KS') or symbol.endswith('.KQ')):
                    processed_symbol = f"{symbol}.KS"
            
            # 통화 정보 결정 - 한국 주식인지 여부 확인
            is_korean_asset = (processed_symbol.endswith('.KS') or processed_symbol.endswith('.KQ'))
            currency = "KRW" if is_korean_asset else "USD"
            
            # 데이터 가져오기
            result = await DataProvider.get_data(processed_symbol, start_date, end_date, asset_type)
            
            if result.get("status") != "success":
                return result
            
            data = result["dataframe"]
            asset_info = result["data"]
            
            # 서버에서 기본 계산 수행 (기존 코드와 호환성 유지)
            # 자산 매수 시뮬레이션
            initial_price = safe_scalar(data.iloc[0]["Close"])
            final_price = safe_scalar(data.iloc[-1]["Close"])
            
            shares_bought = investment_amount / initial_price
            final_value = shares_bought * final_price
            
            profit = final_value - investment_amount
            profit_percentage = (profit / investment_amount) * 100
            
            # 일간 수익률 계산
            data["Daily_Return"] = data["Close"].pct_change()
            
            # 누적 수익률 계산
            data["Cumulative_Return"] = (1 + data["Daily_Return"]).cumprod() - 1
            
            # 최대 낙폭(MDD) 계산
            cumulative_max = data["Close"].cummax()
            drawdown = (data["Close"] - cumulative_max) / cumulative_max
            mdd = safe_scalar(drawdown.min()) * 100
            
            # 수익률 통계
            daily_returns = data["Daily_Return"].dropna()
            volatility = safe_scalar(daily_returns.std()) * (252 ** 0.5) * 100
            sharpe_ratio = (profit_percentage / 365 * len(data)) / volatility if volatility != 0 else 0
            
            # 거래 시뮬레이션 (단순 매수-보유 전략)
            trade_history = [{
                "date": data.index[0].strftime("%Y-%m-%d"),
                "action": "매수",
                "price": round(initial_price, 2),
                "shares": round(shares_bought, 4),
                "value": round(investment_amount, 2),
            }, {
                "date": data.index[-1].strftime("%Y-%m-%d"),
                "action": "평가",
                "price": round(final_price, 2),
                "shares": round(shares_bought, 4),
                "value": round(final_value, 2),
            }]
            
            # 일별 데이터 추가 (프론트엔드 계산용)
            daily_data = []
            
            for idx in range(len(data)):
                date_str = data.index[idx].strftime("%Y-%m-%d")
                
                # 필요한 가격 데이터만 추출
                daily_data.append({
                    "date": date_str,
                    "open": float(safe_scalar(data.iloc[idx]["Open"])) if "Open" in data.columns else float(safe_scalar(data.iloc[idx]["Close"])),
                    "high": float(safe_scalar(data.iloc[idx]["High"])) if "High" in data.columns else float(safe_scalar(data.iloc[idx]["Close"])),
                    "low": float(safe_scalar(data.iloc[idx]["Low"])) if "Low" in data.columns else float(safe_scalar(data.iloc[idx]["Close"])),
                    "close": float(safe_scalar(data.iloc[idx]["Close"])),
                    "volume": float(safe_scalar(data.iloc[idx]["Volume"])) if "Volume" in data.columns else 0
                })
            
            # 기존 결과 형식 유지하면서 일별 데이터 추가
            result = {
                "status": "success",
                "symbol": symbol,
                "name": asset_info["name"],
                "asset_type": asset_info["asset_type"],
                "currency": currency,  # 통화 정보 추가
                "start_date": data.index[0].strftime("%Y-%m-%d"),
                "end_date": data.index[-1].strftime("%Y-%m-%d"),
                "initial_investment": float(investment_amount),
                "initial_price": round(initial_price, 2),
                "final_price": round(final_price, 2),
                "shares_bought": round(shares_bought, 4),
                "final_value": round(final_value, 2),
                "profit": round(profit, 2),
                "profit_percentage": round(profit_percentage, 2),
                "max_drawdown": round(mdd, 2),
                "volatility": round(volatility, 2),
                "sharpe_ratio": round(sharpe_ratio, 2),
                "trade_history": trade_history,
                "daily_data": daily_data  # 일별 데이터 추가
            }
            
            # NumPy 타입 변환
            return convert_numpy_types(result)
        
        except Exception as e:
            logger.error(f"백테스팅 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    def print_backtest_result(result: Dict[str, Any]) -> None:
        """
        백테스팅 결과를 콘솔에 출력합니다.
        
        Args:
            result: 백테스팅 결과 딕셔너리
        """
        if result.get("status") != "success":
            logger.error(f"오류: {result.get('error', '알 수 없는 오류')}")
            return
        
        asset_type_kr = {
            "stock": "주식",
            "crypto": "암호화폐",
            "commodity": "원자재",
            "etf": "ETF", 
            "unknown": "기타 자산"
        }
        
        asset_type = asset_type_kr.get(result.get("asset_type", "unknown"), "자산")
        
        print("\n" + "="*60)
        print(f"📊 {asset_type} 백테스팅 결과: {result['name']} ({result['symbol']})")
        print(f"📅 기간: {result['start_date']} ~ {result['end_date']}")
        print("-"*60)
        
        initial_investment = result['initial_investment']
        initial_price = result['initial_price']
        final_price = result['final_price']
        profit = result['profit']
        profit_percentage = result['profit_percentage']
        max_drawdown = result['max_drawdown']
        volatility = result['volatility']
        sharpe_ratio = result['sharpe_ratio']
        
        print(f"💰 초기 투자금액: {initial_investment:,.0f}원")
        print(f"💵 매수 가격: {initial_price:,.2f}원")
        print(f"💵 최종 가격: {final_price:,.2f}원")
        
        profit_str = f"{profit:,.0f}원 ({profit_percentage:.2f}%)"
        if profit >= 0:
            print(f"📈 수익: {profit_str} (이익)")
        else:
            print(f"📉 수익: {profit_str} (손실)")
        
        print("-"*60)
        print(f"📊 최대 낙폭(MDD): {max_drawdown:.2f}%")
        print(f"📊 변동성: {volatility:.2f}%")
        print(f"📊 샤프 비율: {sharpe_ratio:.2f}")
        
        print("="*60)