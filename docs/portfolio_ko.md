# Remote Crypto Quant / Trader 포트폴리오 (WRSE)

본 문서는 제출용 목차(1\~13)를 기준으로 구성되어 있으며, 필요 시 PDF로 변환해 제출하는 것을 전제로 합니다.

링크:

- 대시보드: <https://hoioioio.github.io/WRSE-QUANT-ENGINE/>
- 데이터 스키마/재현: [reproducibility.md](reproducibility.md)
- GitHub: [레포지토리 루트](../)

## Executive Summary (1p)

WRSE는 크립토 선물(perps) 기반의 시스템 트레이딩 연구/백테스트 엔진입니다. 전진 분석(Walk-forward) OOS 검증과 실행 마찰(수수료/슬리피지/펀딩, 메이커→테이커 폴백) 가정을 포함해, “실전에서 성과가 무너지는 요인”을 백테스트 단계에서부터 다루는 것을 목표로 합니다.
본 문서는 연구/포트폴리오 목적이며, 투자 권유가 아닙니다.

핵심 결과(공개 OOS; 2021–2024):

- AB Hybrid(실행 반영): 누적 +55.74%, CAGR 11.74%, MDD -11.99%, Sharpe 0.78
- Taker-only(스트레스): 누적 +43.10%, CAGR 9.39%, MDD -12.73%, Sharpe 0.64

Quant Portfolio Flow:

```text
Market Research
  -> Strategy Research
  -> Backtesting
  -> Portfolio Construction
  -> Risk Management
  -> Execution
  -> Walk-forward & Validation
  -> Live / Paper Trading
  -> Performance Analysis
```

목차:

- [Executive Summary (1p)](#executive-summary-1p)
- [1. Introduction](#1-introduction)
- [2. Trading System Architecture](#2-trading-system-architecture)
- [3. Market Research](#3-market-research)
- [4. Strategy Research](#4-strategy-research)
- [5. Backtesting Framework](#5-backtesting-framework)
- [6. Portfolio Construction](#6-portfolio-construction)
- [7. Risk Management](#7-risk-management)
- [8. Execution System](#8-execution-system)
- [9. Walk-forward & Validation](#9-walk-forward--validation)
- [10. Live Trading / Paper Trading](#10-live-trading--paper-trading)
- [11. Performance Analysis](#11-performance-analysis)
- [12. Conclusion](#12-conclusion)
- [13. GitHub Repository](#13-github-repository)

## 1. Introduction

WRSE는 크립토 선물(바이낸스 Perpetual Futures) 대상의 시스템 트레이딩 연구/백테스트 엔진입니다.
공개 산출물은 전진 분석 기반 OOS 평가와 실행 마찰 가정(수수료/슬리피지/펀딩/메이커→테이커 폴백)을 중심으로 구성되어 있습니다.

요약:

- 시장: Crypto Futures (perps)
- 전략 유형: 추세 기반(모멘텀/레짐) + 쇼크 이벤트 기반 디리스크/회피
- 형태: 시스템 트레이딩(설정 기반 실행, 재현 가능한 산출물)
- 검증: Walk-forward OOS split
- 실행 고려: maker/taker, 슬리피지, 펀딩, 메이커→테이커 폴백 모델
- 목표: systematic trading 연구/검증 파이프라인과 실행 마찰을 포함한 백테스트

산출물:

- PDF(본 문서): 제출용 1\~13 구조
- GitHub(코드): 엔진/실험/설정/재현 경로
- Report/Dashboard: `docs/assets_public/` 기반 정적 대시보드

범위:

- 시장: 크립토 선물(perps)
- 유니버스: TOML 설정 기반 멀티 에셋
- 검증: 전진 분석 OOS split (train -> 파라미터/비중 고정 -> test)

공개 레포 비포함:

- 원본 시장 데이터(용량/라이선스)
- 개인 운용(trade-level) 로그 및 실거래 API 키

## 2. Trading System Architecture

시스템 구조도(개요):

```text
Market Data (OHLCV / funding / L2 summaries)
  -> Data Storage (cache)
  -> Feature / Signal (Trend + ShockScore)
  -> Strategy Engine (walk-forward: train -> lock -> OOS test)
  -> Risk Management + Portfolio Allocation
  -> Execution Model (maker/taker + slippage + funding)
  -> Reporting (metrics, figures, docs/assets_public/*.json)
  -> Dashboard (docs/index.html)
  -> Monitoring / Logging (public repo: integrity checks + reproducible outputs)
```

핵심 모듈:

- 시그널/피처: [../alpha/shock.py](../alpha/shock.py)
- WFO 엔진: [../backtest/walkforward.py](../backtest/walkforward.py)
- 시뮬레이터: [../backtest/simulators.py](../backtest/simulators.py)
- 실행 모델: [../execution/models.py](../execution/models.py)
- 리포팅: [../report.py](../report.py)
- 산출물 정합성 체크: [../integrity\_check.py](../integrity_check.py)

## 3. Market Research

### 3.1 Data, Universe & Assumptions

입력 데이터(캐시 스키마):

- OHLCV(필수): `bt_{SYMBOL}_{timeframe}.pkl` (pandas DataFrame, `open/high/low/close/volume` 필요)
- Funding(선택): `funding_{SYMBOL}.pkl` (`fundingTime`, `fundingRate`)
- L2 요약(선택): `l2_{SYMBOL}_{timeframe}.csv` (`spread_bps`, `micro_dev_bps`/파생, `imb`)

가정 및 편향 통제:

- 타임스탬프: timezone-naive를 전제로 처리합니다([reproducibility.md](reproducibility.md) 참고).
- 리샘플링: 캐시 timeframe(예: 15m)을 내부에서 4h로 리샘플링하여 신호/리스크 판단을 통일합니다.
- 누락 입력의 처리: funding이 없으면 0으로, L2가 없으면 폴백(단순화된 실행 가정)으로 동작합니다.
- 룩어헤드/스누핑: train 구간에서만 파라미터/비중을 선택하고, test(OOS) 구간은 고정 적용합니다.
- 생존 편향: 유니버스 구성(상장/상폐, 심볼 교체)은 데이터 준비 단계에서 관리하는 것을 전제로 합니다.
- 데이터 품질: 결측/중복/비정상 캔들 처리는 캐시 생성 단계에서 보장하는 것을 전제로 합니다.

주의/범위 외:

- 선물 연속선물 롤링/심볼 롤링은 데이터 준비 단계에서 처리하는 것을 전제로 하며, 공개 레포에서는 별도 구현을 포함하지 않습니다.

### 3.2 Research Focus (Crypto Futures)

본 포트폴리오에서 강조하는 연구 항목:

- 변동성 분석(레짐/급변 국면 포함)
- 펀딩 분석(과열/왜곡 구간의 진입 억제)
- 유동성/실행 마찰(지정가 미체결, 슬리피지)과 성과 민감도
- 수익률/낙폭 분포(rolling 윈도우 기반)
- 상관/동조화(포트폴리오 관점의 동시 손실 위험)
- 시장 레짐 전환(추세/횡보/급변) 구간에서의 성과 분해

공개 리포트는 OOS equity 기반의 이벤트 슬라이스/분포 요약을 중심으로 구성되어 있습니다.

이벤트 슬라이스(예시):

- LUNA 디레버리징(2022-05)
- FTX 파산 쇼크(2022-11)

분포 요약(예시):

- 일간 equity 기반 6개월 롤링 수익률 분포

관련 산출물:

- Equity vs BTC(로그): [assets\_public/equity\_vs\_btc\_log.png](assets_public/equity_vs_btc_log.png)
- WFO OOS Sharpe(연도별): [assets\_public/wfo\_oos\_sharpe.png](assets_public/wfo_oos_sharpe.png)
- 연도별 수익률/낙폭 요약: [assets\_public/yearly\_returns.png](assets_public/yearly_returns.png), [assets\_public/yearly\_mdd.png](assets_public/yearly_mdd.png)

Figure 3-1. Equity vs BTC (log)

!\[Figure 3-1]\(assets\_public/equity\_vs\_btc\_log.png null)

Figure 3-2. WFO OOS Sharpe by split year

!\[Figure 3-2]\(assets\_public/wfo\_oos\_sharpe.png null)

Figure 3-3. Yearly returns (OOS)

!\[Figure 3-3]\(assets\_public/yearly\_returns.png null)

Figure 3-4. Yearly MDD (OOS)

!\[Figure 3-4]\(assets\_public/yearly\_mdd.png null)

## 4. Strategy Research

전략은 컴포넌트를 분리한 뒤, 전진 분석 구간에서 비중을 선택해 조합합니다.

전략 설명 템플릿(전략별 공통):

- Strategy idea
- Signal 정의(피처/필터)
- Entry/Exit 규칙(포지션 방향 포함)
- Position sizing / Risk control
- Backtest result (WFO OOS)

### 4.1 Trend 컴포넌트

요약:

- cache timeframe을 내부에서 상위 타임프레임(4h)으로 리샘플링해 사용합니다.
- 단기/중기 신호가 장기 기준선과 일치할 때만 진입합니다.
- 변동성/ADX/펀딩/쇼크 조건 등으로 참여 구간을 제어합니다.

### 4.2 Shock 컴포넌트(ShockScore)

요약:

- train 구간에서 점프 이벤트를 라벨링하고 Ridge 기반 signed classifier를 학습합니다.
- test 구간에서는 재학습 없이 `shock_score`만 산출합니다.
- 진입 회피/디리스크/실행 보수화에 사용합니다.

### 4.3 조합(Trend + Shock)

요약:

- train 구간에서 `weights_grid`를 탐색합니다.
- 선택된 비중은 다음 test 연도에 고정 적용합니다.

## 5. Backtesting Framework

백테스트는 실전에서 성과가 붕괴하는 주요 원인을 포함하도록 설계되어 있습니다.

- 형태: 바 단위(time-step) 시뮬레이션 기반 이벤트 처리(“체결/포지션/펀딩/청산 조건”을 시간 흐름에 따라 처리)
- 수수료(메이커/테이커)
- 슬리피지
- 펀딩(캐시 존재 시 반영, 없으면 0 가정)
- 미체결 지정가에 대한 maker→taker 폴백 실행 모델
- 멀티 에셋 포트폴리오 시뮬레이션
- Walk-forward OOS only 누적
- 파라미터/비중 탐색은 train 구간에 한정(`weights_grid`, `v2_param_samples`)

설정으로 제어되는 실행/비용 파라미터(예시):

- `[execution].slippage_bps`
- `[execution].maker_fee_rate`, `[execution].taker_fee_rate`
- `[execution].exec_mode` (예: `maker_then_taker`)

구현 참조:

- 시뮬레이터: [../backtest/simulators.py](../backtest/simulators.py)
- WFO 실행: [../backtest/walkforward.py](../backtest/walkforward.py)
- 설정: [../config/strategy\_params.example.toml](../config/strategy_params.example.toml)

비고:

- 레버리지는 시뮬레이션 파라미터로 반영될 수 있으나, 청산(리퀴데이션)까지의 정교한 모델링은 공개 버전에서는 제한적이며 필요 시 별도 확장 항목으로 분리합니다.

## 6. Portfolio Construction

유니버스와 포트폴리오 규칙은 TOML로 정의됩니다.

- 종목: `[data].symbols`
- 최대 동시 보유: `[risk].portfolio_slots`
- Trend/Shock 조합 비중: `[walk_forward].weights_grid`(train에서 선택, test에 고정)
- 변동성 타게팅(옵션): `[risk].enable_vol_targeting` 및 관련 파라미터

현재 공개 버전에서의 구성(요약):

- 멀티 에셋 동시 운용(슬롯 제한)
- 거래당 리스크(`risk_per_trade`) 기반 사이징
- Trend/Shock 조합 비중은 전진 분석으로 선택 및 고정 적용

참조:

- 예시 설정: [../config/strategy\_params.example.toml](../config/strategy_params.example.toml)

향후 확장 후보:

- Risk parity / Kelly sizing / 전략별 자본 배분 고도화
- 리밸런싱 정책을 “전략/레짐 단위”로 분리

## 7. Risk Management

공개 설정/로직 기준으로 포함되는 요소:

- 거래당 리스크 기반 사이징(`risk_per_trade`)
- 컴포넌트별 스탑(`stop_loss_pct_trend`, `stop_loss_pct_shock`)
- 포트폴리오 슬롯(집중도 제어)
- 낙폭 구간 기반 신규 리스크 축소(`dd_threshold_*`, `dd_scale_*`)
- 펀딩 과열 구간 신규 진입 억제(펀딩 캐시 존재 시)

향후 확장 후보:

- 익스포저 상한(심볼/섹터/방향)
- 레버리지 상한 및 포트폴리오 리스크(변동성/상관) 기반 제약
- 몬테카를로/스트레스 기반 리스크 한도 설정

## 8. Execution System

실행 모델은 백테스트에 명시적으로 포함됩니다.

- L2 요약 피처가 있으면 메이커 시도
- 미체결 시 테이커로 폴백(비용 보수 가정)
- 모드에 따라 수수료/슬리피지 적용

공개 버전에서 포함되는 실행 요소(요약):

- maker/taker 비용 차등
- 슬리피지(bps) 가정
- 메이커 미체결을 “테이커 폴백”으로 처리

향후 확장 후보:

- 주문 분할, TWAP/VWAP
- 레이턴시/부분 체결/호가잔량 기반 체결비용 모델 고도화

참조:

- 실행 모델: [../execution/models.py](../execution/models.py)
- L2 요약 스키마: [reproducibility.md](reproducibility.md)

## 9. Walk-forward & Validation

검증 원칙:

- OOS만 누적(리포팅은 test 구간 중심)
- 파라미터/비중은 train 구간에서만 도출
- 설정된 연도 단위 split로 테스트

추가 검증(향후 확장 후보):

- 파라미터 안정성/민감도 분석
- 과적합 점검(리샘플링/부트스트랩)
- 경로 의존성(몬테카를로 재표본) 하한선 평가

산출물:

- WFO split 테이블: [assets\_public/wfo\_splits.json](assets_public/wfo_splits.json)
- WFO OOS Sharpe 그래프: [assets\_public/wfo\_oos\_sharpe.png](assets_public/wfo_oos_sharpe.png)

## 10. Live Trading / Paper Trading

본 레포에는 실거래 키 및 전체 주문 로그가 포함되어 있지 않습니다.

실거래 운영 원칙(전신 시스템 기준):

- 거래소 원장(Source of Truth) 우선
- 포지션/오픈오더 reconcile 사이클
- idempotent order key 사용

Paper trading / 라이브 제출 시 포함 가능한 항목(선택):

- Equity curve / 월별 손익 / 낙폭 / 샤프
- 체결 로그(슬리피지/수수료) 요약
- 익스포저/턴오버/거래 횟수
- 모니터링/알림(이상 탐지, 상태 동기화 실패 감지)

## 11. Performance Analysis

성과 분석에서 사용하는 지표(공개 버전 기준):

- Total Return, CAGR, Sharpe, Sortino, MDD
- (옵션) Win rate(일간), DD 지속일
- Profit factor / Avg trade / Turnover 등 trade-level 로그가 필요해 공개 버전에서는 제한적입니다.

### 11.1 WFO OOS 요약(2021–2024)

Table 11-1. WFO OOS Summary (public)

| 항목     | AB Hybrid(실행 반영) | Taker-only(스트레스) |
| :----- | :--------------: | :--------------: |
| 누적 수익률 |      +55.74%     |      +43.10%     |
| CAGR   |      11.74%      |       9.39%      |
| MDD    |      -11.99%     |      -12.73%     |
| Sharpe |       0.78       |       0.64       |
| 운용 일수  |       1,457      |       1,457      |

Equity 산출물:

- [assets\_public/equity\_ab.json](assets_public/equity_ab.json)
- [assets\_public/equity\_ab\_taker.json](assets_public/equity_ab_taker.json)

그림:

- [assets\_public/equity\_vs\_btc\_log.png](assets_public/equity_vs_btc_log.png)
- 연도별 테이블(대시보드 입력): [assets\_public/yearly\_ab.json](assets_public/yearly_ab.json), [assets\_public/yearly\_ab\_taker.json](assets_public/yearly_ab_taker.json)

### 11.2 공개 지표 관련

- 거래 단위(trade-level) 로그는 공개 레포에 포함하지 않습니다.
- 동일한 cache 데이터가 주어지면 대시보드 산출물 재현을 목표로 합니다.

### 11.3 Monitoring, Ops & Post-trade Analytics

공개 레포에서 확인 가능한 운영 관점 요소:

- 산출물/대시보드 정합성 체크 스크립트: [../integrity\_check.py](../integrity_check.py)
- 공개 equity 요약 검증: [../verify\_portfolio.py](../verify_portfolio.py)

실거래/페이퍼 제출 시 포함 가능 항목(선택):

- 전략별/심볼별 성과 분해(기여도)
- 실행 품질(슬리피지/수수료) 리포트
- 알림/모니터링(상태 동기화 실패, 포지션/오더 불일치 탐지)

## 12. Conclusion

공개 산출물의 핵심:

- 전진 분석 OOS 평가(연도 split, 파라미터/비중 고정)
- 실행 마찰 가정 포함(수수료/슬리피지/펀딩 + maker→taker 폴백)
- 정적 대시보드 입력(JSON) 생성 및 검증 가능
- 리모트 환경에서 재현 가능한 실행 경로 제공([reproducibility.md](reproducibility.md))

한계:

- 원본 데이터 미포함
- 실거래 키/전체 로그 미포함
- 일부 지표/검증(부트스트랩/민감도/거래단위 분석)은 공개 버전에서 제한적

실패 모드(예시)와 대응:

- 레짐 전환으로 인한 파라미터 붕괴: 전진 분석 OOS split로 일반화 성능을 확인하고, 연도별 split 성과를 분리해 확인합니다.
- 실행 마찰 과소평가: AB Hybrid(메이커→테이커 폴백)와 Taker-only(스트레스) 결과를 함께 제시해 민감도를 드러냅니다.
- 데이터 누락/품질 이슈: 입력 스키마를 명시하고(funding/L2 누락 시 폴백), 동일한 캐시 입력에서 산출물이 재현되도록 설계합니다.
- 과적합 위험: train 구간에서만 탐색하고 test(OOS)에 고정 적용합니다. 추가 강건성(부트스트랩/민감도)은 확장 항목으로 분리합니다.

## 13. GitHub Repository

엔트리 포인트:

- 평가 실행: [../cli.py](../cli.py)
- 대시보드 산출물 생성: [../report.py](../report.py)
- 공개 equity 요약 검증: [../verify\_portfolio.py](../verify_portfolio.py)

재현 방법:

- [reproducibility.md](reproducibility.md) 기준으로 cache 입력 준비
- README의 실행 커맨드 수행: [../README.md](../README.md), [../README\_KOR.md](../README_KOR.md)

빠른 실행(레포 루트):

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt

python cli.py wfo --config config/strategy_params.example.toml --write_csv ./outputs
python report.py --config config/strategy_params.example.toml --public
python verify_portfolio.py
```

부록(선택):

- 지표 정의/산출 방식, 파라미터 테이블, 추가 그래프를 “Appendix”로 별도 확장 가능

