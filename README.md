# YouTube Script Extractor with Notion Integration

자동화된 YouTube 스크립트 추출 및 Notion DB 통합 시스템입니다. 특정 키워드가 포함된 최신 YouTube 영상을 찾아 자막을 추출하고, Notion 데이터베이스에 저장합니다.

## 주요 기능

- 설정된 YouTube 채널에서 특정 키워드가 포함된 최신 영상 자동 검색
- 영상 자막(스크립트) 자동 추출
- Notion 데이터베이스에 추출된 스크립트 저장
- 시간 기반 자동화 스케줄링 (요일 및 시간대별 설정)
- 중복 스크립트 추출 방지 및 자동 활성화/비활성화 기능

## 시스템 요구사항

- Python 3.10 이상
- Docker 및 Docker Compose
- Notion API 키 및 데이터베이스 ID
- 인터넷 연결

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/yourusername/youtube-script-extractor.git
cd youtube-script-extractor
```

### 2. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 필요한 값을 입력합니다:

```bash
cp .env.example .env
```

아래 항목들을 적절히 입력하세요:

```
NOTION_API_KEY=your_notion_api_key
REFERENCE_DB_ID=your_reference_db_id
SCRIPT_DB_ID=your_script_db_id
```

### 3. Docker를 사용한 실행

```bash
docker-compose up -d
```

## Notion 데이터베이스 설정

### 참고용 DB 구조

다음 속성을 가진 Notion 데이터베이스가 필요합니다:

- `제목` (title): 검색할 키워드
- `URL` (url): YouTube 채널 URL
- `채널명` (select): 채널 이름
- `활성화` (checkbox): 활성화/비활성화 상태
- `시간` (number): 영상이 일반적으로 업로드되는 시간 (0-23, 정수)

### 스크립트 DB 구조

스크립트 저장을 위한 Notion 데이터베이스는 다음 속성을 가져야 합니다:

- `제목` (title): 검색 키워드
- `URL` (url): YouTube 영상 URL
- `영상 날짜` (date): 영상 업로드 날짜
- `채널명` (select): 채널 이름
- `영상 길이` (rich_text): 영상 길이 정보
- `상태` (select): 처리 상태 (분석/완료)

## 사용 방법

### 스케줄링 작동 방식

1. **자동 스케줄링**: 애플리케이션이 시작되면 내장된 스케줄러가 자동으로 시작됩니다.
   - 매일 새벽 4시: 모든 채널을 활성화 상태로 재설정
   - 오전 영상(시간 < 12): 9시, 10시, 11시에 스크립트 추출 시도
   - 오후 영상(12 ≤ 시간 < 20): 업로드 시간 + 2/3/4 시간 후에 추출 시도
   - 늦은 저녁 영상(시간 ≥ 20): 22시, 23시, 0시, 1시, 2시, 3시에 추출 시도
   - 주말(토, 일)에는 실행되지 않음

2. **수동 실행**: API 엔드포인트를 통해 수동으로 스크립트 추출을 시작할 수 있습니다.

### API 엔드포인트

- **GET `/`**: API 상태 확인
- **POST `/sync-notion-db`**: 모든 활성화된 채널에 대해 스크립트 추출 작업 시작
- **POST `/test-scheduler`**: 특정 시간 시뮬레이션 (테스트용)

## 코드 구성

- **main.py**: FastAPI 애플리케이션 및 라우트 정의
- **youtube_utils.py**: YouTube 동영상 및 스크립트 처리 기능
- **notion_utils.py**: Notion API 연동 기능
- **scheduler.py**: 자동화 스케줄링 로직


## 라이센스

This project is licensed under the MIT License - see the LICENSE file for details.