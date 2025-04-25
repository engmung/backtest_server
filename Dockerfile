# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지 설치 (matplotlib 및 기타 패키지에 필요한 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libblas-dev \
    liblapack-dev \
    libpng-dev \
    pkg-config \
    fonts-nanum \
    # 한글 폰트 추가
    fonts-noto-cjk \
    # 글꼴 캐시 업데이트 도구
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    # 글꼴 캐시 업데이트
    && fc-cache -fv

# 필요한 Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 포트 설정
EXPOSE 8010

# 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]