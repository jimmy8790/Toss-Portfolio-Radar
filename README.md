<<<<<<< HEAD
# Toss Portfolio Radar

Toss Portfolio Radar는 토스증권 Open API를 이용해 보유 주식을 조회하고, 각 종목의 단기 추세, 변동성, 하락위험 점수를 로컬 Streamlit 화면에 표시하는 조회 전용 포트폴리오 대시보드입니다.

이 프로젝트는 실제 주문, 자동매매, 주문 정정, 주문 취소 기능을 제공하지 않습니다. 표시되는 점수와 문구는 투자 판단을 대신하지 않는 참고용 정보입니다.

## 주요 기능

- 토스증권 Open API OAuth 토큰 발급 및 메모리 캐싱
- 계좌 목록과 보유 종목 조회
- 현재가, 일봉 캔들, USD/KRW 참고 환율, 종목별 유의사항 조회
- 추세 점수, 변동성 점수, 하락위험 점수 계산
- 포트폴리오 요약 카드와 종목별 테이블 표시
- 종목 상세 가격 차트, 이동평균선, RSI 차트 표시
- RSI, 변동성, 최대낙폭 등 생소한 지표의 간단 설명 표시
- 최근 흐름과 변동성을 이용한 2~3거래일 참고 시나리오 차트 표시
- 관심종목을 `watchlist.json`에 저장하고 보유 종목과 별도로 분석
- 포트폴리오 snapshot을 이용한 총 평가금액, 누적 손익률, 평균 하락위험점수 변화 그래프
- 미국 주식의 USD 평가금액과 KRW 환산 평가금액 표시
- 미국 주식의 USD 기준 수익률, KRW 기준 수익률, 환율 효과, 추정 매수 환율 표시
- 국내/미국 장 운영 상태를 사이드바에 상시 표시
- API 오류, 빈 계좌, 빈 보유 종목, 설정 누락 상황에 대한 안내 UI
- 사용자가 설정한 초 단위 자동 새로고침

## 기술 스택

- Python 3.11+
- Streamlit
- httpx
- pandas
- numpy
- python-dotenv
- plotly
- pytest

## 설치 방법

명령어를 직접 입력하지 않고 실행하려면 아래 방법을 권장합니다.

1. 파일 탐색기에서 `toss-portfolio-radar` 폴더를 엽니다.
2. `run_app.bat` 파일을 더블클릭합니다.
3. 처음 실행할 때 자동으로 `.venv` 가상환경을 만들고 필요한 패키지를 설치합니다.
4. 설치가 끝나면 Streamlit 앱이 실행됩니다.
5. 브라우저에서 `http://localhost:8501`로 접속합니다.

`run_app.bat`은 `.env` 파일이 없으면 `.env.example`을 복사해 자동으로 만들어 둡니다.
API 키가 아직 없어도 앱은 실행되며, 화면에 설정 안내가 표시됩니다.

수동으로 설치하고 싶은 경우에는 아래 명령어를 사용합니다.

```bash
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

Windows PowerShell 기준:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

브라우저에서 다음 주소로 접속합니다.

```text
http://localhost:8501
```

## .env 설정 방법

`.env.example`을 복사해 `.env` 파일을 만든 뒤 토스증권 Open API 클라이언트 정보를 입력합니다.
`run_app.bat`을 먼저 실행했다면 `.env` 파일이 이미 만들어져 있을 수 있습니다.

```env
TOSS_CLIENT_ID=your_client_id_here
TOSS_CLIENT_SECRET=your_client_secret_here
```

API 키와 시크릿은 코드, README, 테스트 코드, Git 커밋에 절대 포함하지 마세요.

## 실행 방법

가장 쉬운 실행 방법:

```text
run_app.bat 더블클릭
```

더블클릭 실행 후 브라우저에서 다음 주소로 접속합니다.

```text
http://localhost:8501
```

앱 왼쪽 사이드바에서 `자동 새로고침`을 켜고 `새로고침 간격(초)`을 설정하면 해당 간격마다 화면을 자동으로 다시 불러옵니다.
자동 새로고침 설정은 URL에 저장되어 화면이 다시 불러와져도 유지됩니다.
자동 새로고침은 브라우저 전체를 새로고침하지 않고 포트폴리오 데이터 영역만 부분 갱신합니다.
API 호출 한도 초과를 피하려면 너무 짧은 간격은 피하는 것이 좋습니다.

사이드바의 `☰ 메뉴`에서 화면을 분리해서 볼 수 있습니다.

- `포트폴리오`: 보유 종목, 요약 카드, 환율 영향, 종목 상세 분석
- `관심종목`: `watchlist.json` 기반 관심종목 추가/삭제와 점수 분석
- `변화 그래프`: 저장된 `snapshots.json` 기반 포트폴리오 변화 그래프

국내/미국 장 운영 상태는 별도 메뉴가 아니라 왼쪽 사이드바에 기본으로 표시됩니다.

수동 실행:

```bash
streamlit run app.py
```

PowerShell에서 Python 환경이 여러 개라면 아래처럼 실행하는 편이 안전합니다.

```powershell
python -m streamlit run app.py
```

실행이 안 될 때 확인할 것:

- `run_app.bat`을 프로젝트 폴더 안에서 실행했는지 확인합니다.
- Python 3.11 이상이 설치되어 있는지 확인합니다.
- 패키지 설치 중 실패했다면 인터넷 연결을 확인한 뒤 `run_app.bat`을 다시 더블클릭합니다.
- pandas 같은 패키지가 없다고 나오면 `run_app.bat`을 다시 실행해 의존성을 재설치합니다.
- `.env`에 API 정보를 입력했는데 계좌가 안 보이면 앱 화면의 `새로고침` 버튼을 누르거나, 실행 창을 닫고 `run_app.bat`을 다시 더블클릭합니다.
- 앱 왼쪽 사이드바의 `API 연결 진단` 버튼을 누르면 토큰 발급 성공 여부와 계좌 API 결과를 민감정보 없이 확인할 수 있습니다.
- 계좌 목록이 계속 비어 있으면 토스증권 Open API에서 계좌 조회 권한이 활성화되어 있는지, 해당 API 키가 실제 계좌와 연결되어 있는지 확인합니다.

## 테스트 실행 방법

```bash
pytest
```

## 폴더 구조

```text
toss-portfolio-radar/
  app.py
  run_app.bat
  watchlist.json
  requirements.txt
  README.md
  .gitignore
  .env.example
  src/
    __init__.py
    config.py
    toss_client.py
    indicators.py
    risk_model.py
    portfolio.py
    formatting.py
  tests/
    test_indicators.py
    test_risk_model.py
```

## 주의사항

- 이 프로젝트는 조회 전용입니다.
- 주문, 자동매매, 주문 정정, 주문 취소 기능은 없습니다.
- 이 프로젝트는 투자 조언이 아닙니다.
- 점수는 정확한 가격 예측이 아니라 최근 데이터 기반 참고 지표입니다.
- 단기 시나리오 차트는 최근 흐름과 변동성으로 만든 참고용 범위이며 특정 가격이나 방향을 보장하지 않습니다.
- `snapshots.json`에는 평가금액 같은 개인 포트폴리오 정보가 저장될 수 있으므로 Git에 올리지 마세요.
- API 키와 시크릿을 절대 Git에 올리지 마세요.
- access token, client secret, 계좌번호 같은 민감정보를 화면이나 로그에 노출하지 않도록 주의하세요.
=======
# Toss-Portfolio-Radar
Toss Portfolio Radar는 토스증권 Open API를 이용해 보유 주식을 조회하고, 각 종목의 단기 추세, 변동성, 하락위험 점수를 로컬 Streamlit 화면에 표시하는 조회 전용 포트폴리오 대시보드 입니다.
>>>>>>> 5c95b4c9980712797a1d7b2870baaa3a555e74eb
