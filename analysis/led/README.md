# LED 런: PMT gain

`gain.py`: 데이터셋의 LED 런 전체(run sheet 종류 "LED")로 gain vs HV를 구합니다.
- LED(spe) 런: SPE 피크를 직접 맞춤(pedestal + Poisson 합).
- LED(~10pe), LED(6-38) 런: 광통계법. SPE 상대 폭은 직접 맞춘 값(2000 V 이상)을 씁니다.
- G = k·HV^β를 맞추고 운전 HV에서의 gain을 냅니다.

```bash
analysis/led/gain.py --dataset Y2026A --out DIR           # 추출 + 맞춤 (16 프로세스, 약 20초)
analysis/led/gain.py --dataset Y2026A --out DIR --refit   # DIR/led_charges.json에서 맞춤만
```
출력: `led_charges.json`, `led_gain.json`(결과), `spe_fits.png`, `gain_vs_hv.png`.

Y2026A 결과(2026-11-27): A β 5.96, 1680 V에서 6.15×10⁶ = 0.98 pC. B β 6.18, 1642 V에서 7.10×10⁶ = 1.14 pC. SPE 상대 폭 0.38 / 0.37.

창 설정은 Y2026A LED 설정(`LED_PMT_gain_check.config`: 1008샘플 기록, LED 동기 트리거 FADC ch3, LED 펄스 약 366번 샘플)에 맞춘 것입니다.
다른 데이터셋에 쓰기 전에 확인하세요.
