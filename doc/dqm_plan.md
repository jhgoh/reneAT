# DQM 그림 정리 계획

2026-11-27 정리. DQM 웹페이지(`index.html` 묶음)를 꾸미기 전에, 그 안에 들어갈 그림 목록부터 확정하려고 적어 둔 메모예요. 아직 구현 전이에요.

## 1. 모든 런에 공통

| 페이지 | 내용 | 지금 상태 |
|---|---|---|
| 요약 표 | livetime, rate, 노이즈, 짝수/홀수, 현장 SPE, 실효 문턱, flag 목록 | 새로 |
| overview | 트리거 rate vs 시간, 1초당 트리거, TCB·TrgNum 점검, 데드타임 | 있음 |
| adc | baseline, 무작위 노이즈, 짝수/홀수 평균·흔들림, 8샘플 패턴 크기 vs 시간 | 있음. 8자리 모양 그림은 flag 때만 |
| pmt | 현장 SPE, gain vs 시간, 실효 문턱, 문턱 규칙 불일치, 보드 pedestal, 설정 변화 | 가짜 비율 추가 |
| fadc | Qsum 스펙트럼, A/B 비, 앞쪽 가장자리·rise, 포화 비율 | 있음 |
| veto | SADC 채널 rate, 다중도, baseline | 있음 |

### 현장 SPE
- 트리거 앞 pedestal 창(샘플 0–99)의 외딴 단일 펄스를 써요. 높이 ≥ 5 ADC이고, 전하는 피크 −4부터 +12샘플까지 합해요.
- 가짜 비율은 같은 기준을 뒤집은 파형에 적용해서 재요(반대 극성 대조).
  - 4185 A/B 약 0%, 4223 A/B 11%/8%, 4370 A 84%(노이즈 2.9), 4370 B 약 0%
- 가짜 비율이 5%를 넘으면 그 채널의 SPE 값은 표시만 하고 gain flag는 꺼요.
- 절대 gain은 LED 런에서 정해요. 현장 SPE는 문턱 때문에 LED보다 10–20% 낮게 나와서, 런 사이 상대 변화를 보는 용도예요.
- 4223에서 뒤집은 파형에 걸리는 펄스(약 0.9 pC)는 pedestal 창 겹침으로 baseline이 찌그러진 탓으로 추정해요. 아직 확인 전이에요.

## 2. 런 종류별 (run sheet `run_type`으로 선택, 정기적으로 받는 런만)

| 종류 | 특화 그림 | 관련 커미셔닝 단계 |
|---|---|---|
| source | 소스 피크 fit(위치·폭), 가까운 background 런을 뺀 스펙트럼, 소스 위치별 A/B 비, 소스 rate | 3–5 |
| background | 기준 런과 스펙트럼 비교, rate 안정성, 뮤온 rate, 뮤온 뒤 중성자, 지연 쌍 후보 | 6–10 |
| veto 테스트 | veto 중심, 패널별 효율·문턱 | 8 |

### 일반성이 떨어지는 런은 DQM 밖에서 전용 분석으로
- 대상: LED 런(HV 스캔, SPE 런), 레이저 런, 그 밖의 시험 런
  - 횟수가 적고, 런마다 설정이 달라요. 예: LED는 1008샘플 기록, LED 동기 트리거(ch3), 펄스 약 366번 샘플
  - 결과도 런 하나가 아니라 런 묶음(HV 스캔 전체)으로 나와요
- 처리 방식
  - 공통 페이지는 이런 런에도 자동으로 그려요. 설정이 정상인지, 노이즈와 짝수/홀수 상태는 어떤지 확인하는 용도예요.
  - 측정 자체(gain vs HV, 선형성)는 전용 분석 스크립트로 해요. reneAT 하위 명령이나 `analysis/` 아래 스크립트로 두고, 런 목록과 창 설정을 인자로 받아요.
  - 결과 숫자(예: 운전 HV gain)는 DQM이 읽는 기준값으로 남겨요. 그러면 현장 SPE와 LED gain 비교 같은 것을 DQM에서 쓸 수 있어요.
- 지금 있는 것: LED gain 분석 스크립트(2단계, 아직 scratchpad). 정식 위치로 옮길 예정
- 레이저: 측정 조건 관리가 어려웠던 데이터라 지금은 다루지 않아요. 나중에 새로 측정하면 전용 분석으로 추가해요.

## 3. Trend
- 점 색은 런 종류별로 나눠요.
- 같은 종류끼리 비교하는 패널을 따로 둬요. 예: Cs-137 피크 위치, background rate.
- 중복 패널을 합쳐요.
  - 짝수/홀수 `pedeo_median`과 `eo_mean`은 하나로
  - pedestal 중앙값은 보드 pedestal 패널로
  - Qsum/height는 rise 패널에서 빼기
- 남길 것:
  - rate, 노이즈, 짝수/홀수, 8샘플 패턴
  - SPE(가짜 비율 표시), 실효 문턱
  - Qsum 중앙값(종류별), A/B 비, 앞쪽 가장자리
  - 포화 비율, 데드타임 비율, livetime, flag 수

## 4. 조사용 그림 (루틴 제외)
- 대상: eo_survey, eo_bytype, eo_per_event, fixed_phase_spectrum, slots, fixed_phase_before_after, period_patterns, prepulse, turnon, deadtime, RAW 비교
- 결론은 이슈 #6에 있어요. 그림은 스크립트와 함께 `doc/commissioning/stage1/`에 보관할 예정이에요.
- fixed_phase_spectrum과 slots는 16 ns 위상을 맞춰 다시 그린 뒤 보관해요.

## 5. prompt와 DQM의 역할 나누기
- **prompt**: subrun마다 PRD 파형을 한 번 읽어요. 파형이 있어야 하는 계산은 모두 여기서 해요.
  - 이벤트별 양(ntuple)
  - subrun 히스토그램과 요약
- **DQM**: prompt 출력만 읽어요. 파형을 다시 읽지 않아요.
  - 런 하나 안의 그림, flag
  - 여러 런을 함께 쓰는 것: background 빼기, 기준 런 비교, trend

### 런 종류별 그림을 위해 prompt에 더할 것
- [ ] 뒤집은 파형 단일 펄스 히스토그램(SPE 가짜 비율)
- [ ] subrun 평균 파형(채널별, 높이 구간별, 앞쪽 가장자리 기준 정렬): 펄스 모양, A·B 시간
- [ ] 트리거 펄스 뒤 창의 펄스 수와 시간 분포: afterpulse. 앞 트리거와의 시간 간격별 단일 펄스 수: dark rate와 상관 펄스 구분
- [ ] 기록 길이나 트리거 설정이 다른 런(LED 등)에서 prompt가 깨지지 않게 하기. 측정용 창은 전용 분석에서 정해요
- [ ] prompt 출력 버전 번호: DQM이 오래된 출력을 알아보고 다시 돌릴지 판단

### DQM만으로 되는 것 (prompt ntuple에 이미 있음)
- source 피크 fit, A/B 비: `Qsum_c`, `Qgm`
- 소스 rate, background 빼기: 다른 런의 prompt 출력을 같이 읽어서
- 뮤온 rate, 뮤온 뒤 중성자, 지연 쌍: `NVeto`, `DtPrevMuon`, `DtPrevFADC`
- 포화: `Height_c`, `Sat_c`

