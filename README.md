# reneAT: RENE data analysis tools
A lightweight production and analysis tools for RENE experiment

## 분석 도구 `python/` (데이터·MC 공통)
공식 PRD 파일(데이터)과 renesim이 만드는 PRD 형식 MC를 **같은 코드**로 읽고 재구성합니다.
데이터와 MC가 같은 정의(`qsum.compute_channel`)를 거치므로 바로 겹쳐 볼 수 있습니다.

```bash
mamba activate hep2026.01
source /path/to/reneAT/setup.sh          # PYTHONPATH(python/), PATH(bin/) 설정

reneat runs --source Cs137 --first 4100 --last 4240         # 런 카탈로그 조회 (bad run 제외)
reneat ntuple 4185 -o data_4185.root --max-events 400000      # 데이터 런 -> feature ntuple
reneat ntuple 'mc/prd_src_Cs137_*.root' -o mc_Cs137.root      # MC 파일 -> 같은 형식
reneat source-compare --src data_4185.root --bkg 4063 --mc mc_Cs137.root -o cs137.png   # MC 스케일 fit

# 여러 선원을 한 장에: 배경 뺀 데이터 vs 생성한 그대로의 MC (스케일 없이 면적만 맞춤)
reneat overview --set Cs137 data_4185.root data_4099.root mc_Cs137.root \
                --set AmBe  data_4223.root data_4237.root - \
                --logy AmBe -o overview.png
```

| 모듈 | 내용 |
|------|------|
| `python/prd.py` | PRD 파일 찾기(`run_files`), 청크 단위 읽기, 채널 맵 (ch0 = PMT A, ch1 = PMT B) |
| `python/catalog.py` | DAQ 런 카탈로그(sqlite, 읽기 전용), bad run 목록, 선원 이름 파싱 |
| `python/qsum.py` | pedestal, Qsum, Qtail, fired bin, 펄스 높이·위치 |
| `python/ntuple.py` | 트리거별 feature ntuple. 데이터는 livetime, MC는 생성 사건 수와 truth(Equench, NPE 등)를 함께 저장 |
| `python/compare.py` | 라이브타임 정규화 배경 빼기, MC 스케일 fit, A/B 비, 평균 펄스 모양 |
| `python/prompt.py` | sub-run 단위 prompt 처리 (FADC feature 트리 + 점검·히스토그램 요약) |
| `python/dqm.py` | 런 단위 DQM 페이지, 런 간 trend |
| `python/runsheet.py` | offline good-run 시트 (CSV 캐시, 런 종류·데이터셋) |
| `python/pipeline.py` | 런 전체 병렬 처리, SLURM 제출, 전송 끝난 런 찾기(`watch`) |

- 데이터 livetime = 읽은 이벤트들의 TCBTRGTime 경과 시간. TCBTRGTime은 ns 단위이고 2^24 µs(16.78 s)마다
  되감기므로 이를 풀어서 더합니다 (`prd.TCBClock`). TrgNum은 긴 런 안에서 다시 시작하고(예: 4099),
  카탈로그 `nfadc`는 PRD 이벤트 수와 다를 수 있어(예: 4185) 쓰지 않습니다.
- 경로는 환경변수 `RENE_PRD`, `RENE_DB`, `RENE_CONFIG`로 바꿀 수 있습니다 (기본: `/store/cpnr-data/RENE/...`).
- 파이썬에서 직접 쓸 때는 `setup.sh` 후 `import ntuple, compare` 처럼 불러옵니다.
- Qsum 정의(pedestal 0–99, 신호 100–349, tail 300–349 샘플)는 W.J. Lee의 ChargeSum을 따릅니다 (`qsum.QSumConfig`).
- FADC는 짝수 샘플을 홀수 샘플보다 일정하게 높게 기록합니다 (PMT A 약 +4, B 약 +1 counts; 500 MS/s ADC의 두 샘플 경로 차이로 추정).
  기본값 `ped_mode="parity"`는 이벤트마다 짝수·홀수 샘플의 pedestal을 따로 구해 각각 뺍니다. 짝수 길이 창의 합(Qsum, Qtail)은
  `single`과 같고, 펄스 높이·fired·`PedRMS`(남은 무작위 노이즈)가 달라집니다. 그 차이는 `PedEO`로 남깁니다.
- 채널 간 시간 비교는 펄스 최댓값(`Peak`)이 아니라 앞쪽 가장자리(`Fired`) 기준으로 합니다. 2026-06-14(런 4232와 4234 사이)부터
  PMT A 펄스 뒤에 약 60 ns 간격의 반복 펄스가 생겨 최댓값 위치가 늦어졌지만, 앞쪽 가장자리는 A, B 모두 그대로입니다.

### Prompt 처리와 data quality monitoring
PRD 런 전송이 끝나면 런의 모든 엔트리를 한 번 읽어(`prompt`) sub-run마다 결과를 남기고,
이를 모아 런 단위 DQM 페이지와 런 간 trend를 만듭니다(`dqm`, `trend`). 출력 위치는 `--out` 또는 `RENE_PROMPT`.

```bash
export RENE_PROMPT=/path/to/prompt              # 출력 위치
reneat prompt 4370 -j 24                        # 로컬 병렬 처리 (하루 런: FADC 런 ~3분, veto 런 ~10분)
reneat dqm 4370                                 # $RENE_PROMPT/dqm/004370/index.html, 그리고 trend 갱신
reneat submit 4370                              # SLURM: prompt array job -> dqm + trend job
reneat watch --first 4370 --mode slurm          # 전송이 끝난 런을 찾아 처리 (cron 용)
reneat watch --first 4370 --dry-run             # 처리할 런만 보기
```

- `prompt`: `<out>/<run>/prompt_<run>.<sub>.root`. 출력이 이미 있는 sub-run은 건너뜁니다 (`--overwrite`).
  - `FADC` 트리: FADC 트리거마다 QSum feature(A, B), 포화 여부, `Qgm = sqrt(QsumA*QsumB)`,
    같은 엔트리의 veto 채널 수, 직전 FADC 트리거 / veto 히트 / muon-like(EventType 3)까지의 시간 [us].
  - `summary` (JSON): 엔트리 수, EventType별 개수, TCB 시계와 TrgNum 점검, 1초 단위 계수,
    FADC pedestal·노이즈·펄스 위치·Qsum 히스토그램, SADC 채널별 히트 수·스펙트럼·baseline·다중도·동시 히트.
  - 읽을 수 없는 파일은 오류만 기록하고 넘어갑니다.
- `dqm`: `overview.png`(계수율, 시계·트리거 번호 점검, 런 정보), `fadc.png`, `veto.png`, `prompt.png`(시간 상관, delayed 쌍),
  `summary.json`, `index.html`. 처리되지 않은 sub-run, 읽을 수 없는 파일, 1초 이상 트리거 공백, 계수율 급감 등을 flag로 표시합니다.
- `trend`: `<out>/dqm/trend.csv`, `trend.png`, 전체 런 표 `index.html`.
- `watch`: PRD 파일이 `--min-age`(기본 2시간) 동안 바뀌지 않았고 카탈로그에 종료 시각이 있는 런 가운데
  DQM이 없거나 PRD보다 오래된 런을 처리합니다. cron 예:
  `0 * * * * bash -lc 'mamba activate hep2026.01; source /path/to/reneAT/setup.sh; RENE_PROMPT=/path/to/prompt reneat watch --first 4370 --mode slurm' >> watch.log 2>&1`
- 시간: 런 안의 시간은 TCB 경과 시간이고, sub-run 사이는 앞 sub-run 마지막과 다음 sub-run 첫 엔트리의 TCB 차이(16.78 s 주기)로 잇습니다.
  veto 채널은 SADC 채널 번호(1부터)와 `S_PmtID`로만 표시합니다.

### 프롬프트 분석 `analysis/`
LED, 선원, veto 테스트처럼 런 종류마다 보는 변수가 다르고 그 결과로 세팅·보정값을 정하는 분석은 `analysis/<종류>/`에 둡니다.
모든 런에 똑같이 만드는 그림은 DQM에 둡니다. 자세한 구분은 `analysis/README.md`, `doc/dqm_plan.md`.

```bash
analysis/led/gain.py --dataset Y2026A --out DIR   # LED HV 스캔: gain vs HV, 운전 HV gain
```

### 런 정보: offline good-run 시트
Google 시트(데이터셋 탭마다 런별 Source, Detector, HV, THR, Description, Data issue)를 공개 CSV로 받아 로컬에 캐시합니다.
주소는 `RENE_RUNSHEET`(git에 넣지 않는 `site.sh`에 적음; `site.sh.example`을 복사해서 씀), 캐시는 `RENE_RUNSHEET_CACHE`(기본 reneAT 안의 `cache/runsheet`, git에는 넣지 않음).
인터넷이 없는 계산 노드에서는 마지막으로 받은 캐시를 씁니다.

```bash
reneat runsheet --update                  # 시트를 새로 받음
reneat runsheet                           # 데이터셋 목록과 런 수
reneat runsheet 4237 4370                 # 런별 행 (시트에 적힌 그대로)
reneat runs --first 4200 --type source    # 카탈로그 + 시트: 데이터셋, 종류, Source, Data issue
reneat runs --dataset H2025C --type LED
```

- 런 종류(`type`): `source`(동위원소·AmBe·Cf·Duran 표기), `no source`("-", "BKG"), `LED`, `laser`(Laser module 데이터셋, "Laser ..."),
  `veto test`(veto 시험 데이터셋), `blank`(Source 칸 비어 있음), `other`. Source 이름은 시트에 적힌 그대로 둡니다.
- `dqm`은 데이터셋·종류·Source를 페이지와 trend 표에 넣고, Data issue 칸이 있으면 flag로 보여 줍니다.

> PRD 제작은 별도의 공식 production 코드로 이루어집니다. 아래의 `Production/` 내용은 이전 자체 제작 도구로, 정리 예정입니다.

RENE실험 데이터 분석을 위하여 RAW데이터로부터 flat ntuple을 생성합니다.
RENE실험의 RAW데이터 형식은 CUPDAQ를 기반으로 하며, FADC와 SADC 파일로 나뉘어 생성됩니다.
데이터 분석의 편의성을 위하여 이를 하나로 합치고, flat ntuple형식으로 변환합니다.

## Directory structure
```
Production/
├── raw2flat.py         # Main production script
├── RawObjs/            # CUPDAQ raw data format library (C++)
├── EventMatcher/       # C++ event matching and tree filling library
├── python/
│   ├── logreader.py    # TCB log parser
│   └── runinfo.py      # Run configuration container
├── test/
│   ├── flat2flat.py        # PRD 재압축 및 채널 드롭 변환
│   ├── comparePRD.py       # 두 PRD 파일의 내용 비교 검증
│   ├── submit_flat2flat.sh # flat2flat SLURM 배치 제출
│   ├── run_flat2flat.sh    # flat2flat SLURM 잡 스크립트
│   └── run_comparePRD.sh   # comparePRD SLURM 잡 스크립트
├── RAW -> ...          # Symlink to raw data
├── TCBLOG -> ...       # Symlink to TCB log files
└── PRD/                # Output flat ntuples (or symlink)
```

## Flat analysis ntuple production
RAW 데이터로부터 flat ntuple을 생성합니다. 다음 순서로 진행합니다.

- (로그인 할 때마다) hep2026.01 mamba환경 진입
- (한번만) `libRawObjs.so` 라이브러리 파일 빌드
- (한번만) 데이터 디렉토리 링크 및 출력 디렉토리 설정
- `raw2flat.py` 를 이용해 RAW 파일을 flat ntuple 생성

### Initial setup
#### 1. 라이브러리 빌드
먼저 `libRawObjs.so`와 `libEventMatcher.so` 파일을 빌드합니다.
`libEventMatcher.so`는 `libRawObjs.so`에 의존하므로 순서대로 빌드합니다.

경희대 환경에서는 mamba를 이용하여 root 및 관련 패키지를 사용합니다.
잘 되지 않으면 아래 Troubleshooting 섹션을 확인 해 보세요.
```bash
mamba activate hep2026.01 ## 로그인 할 때마다.
export LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production/RawObjs
make clean && make

cd ../EventMatcher
make clean && make
```
위 명령어 실행 뒤 `Production/RawObjs/libRawObjs.so`와 `Production/EventMatcher/libEventMatcher.so` 파일이 생성되어 있어야 합니다.

#### 2. 데이터 디렉토리 링크 및 출력 디렉토리 설정
`raw2flat.py`는 `Production/` 아래에 다음 세 디렉토리가 있어야 합니다.

| 디렉토리 | 용도 | 설정 방법 |
|----------|------|-----------|
| `RAW/`   | FADC/SADC raw 데이터 입력 | symlink 필수 |
| `TCBLOG/` | TCB 로그 파일 (run config 추출) | symlink 필수 |
| `PRD/`   | flat ntuple 출력 | `mkdir` 또는 symlink |

경희대 환경에서의 설정 예시입니다. 경로는 시스템에 따라 달라질 수 있습니다.
```bash
cd Production
ln -s /store/cpnr-data/RENE/RAW
ln -s /store/cpnr-data/RENE/DAQLOG/TCB TCBLOG
mkdir PRD
```

`PRD/`는 로컬에 만드는 것이 기본입니다. 중앙 저장소에 바로 쓰려는 경우에는 `mkdir` 대신 symlink를 사용할 수 있습니다. 이 경우 해당 디렉토리에 대한 쓰기 권한이 있어야 합니다.
```bash
ln -s /store/cpnr-data/RENE/PRD/ PRD
```


### Production
아래와 같이 production을 진행합니다.
```bash
mamba activate hep2026.01 ## 로그인 할 때마다.
export LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production
./raw2flat.py <RUN_NUMBER>
```

batch job으로 실행하는 경우, 그리고 progress-bar가 필요없는 경우는 `--no-progress` 옵션을 붙여 실행합니다. 자세한 디버깅 메시지가 필요 없으면 `--no-verbose` 옵션을 붙이면 됩니다.

### Size reduction and validation (flat2flat / comparePRD)
PRD 파일의 크기 축소 및 검증은 `test/` 디렉토리의 스크립트를 사용합니다. SLURM 배치로 제출하는 경우:
```bash
cd Production/test
./submit_flat2flat.sh <RUN_NUMBER>     # 파일 크기 축소 배치 제출
sbatch run_comparePRD.sh <RUN_NUMBER>  # 두 PRD 파일 내용 비교 검증
```

## Troubleshooting
### mamba 환경 동작 문제
micromamba를 이용합니다. `mamba activate hep2026.01` 이 동작하지 않으면,
`~/.bashrc` 파일에 아래 내용을 추가한 다음 다시 로그인 뒤 재시도 해 봅니다.

```bash
# >>> mamba initialize >>>
# !! Contents within this block are managed by 'mamba shell init' !!
export MAMBA_EXE='/store/sw/miniconda3/bin/mamba';
export MAMBA_ROOT_PREFIX='/store/sw/miniconda3';
__mamba_setup="$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__mamba_setup"
else
    alias mamba="$MAMBA_EXE"  # Fallback on help from mamba activate
fi
unset __mamba_setup
# <<< mamba initialize <<<
```

경희대 환경 외의 다른 리눅스 환경에서 실행한다면 mamba 환경이 세팅되어 있지 않을 수 있습니다.
hep2026.01 환경은 아래 명령어를 이용할 수 있습니다. 
`environment.yml` 파일은 본 repository에서 찾을 수 있습니다.
```bash
mamba env create -f environment.yml
```

### 실행시 라이브러리 로딩 문제
- `LANG=C`일때 라이브러리 로딩 문제:
  - 증상: 다음과 같은 메시지 발생하며 진행 안됨. `Error in cling::AutoLoadingVisitor::InsertIntoAutoLoadingState:\n Missing FileEntry for RawObjs/AbsChannel.hh\n   requested to autoload type AbsChannel`
  - 해결방법:`LANG=en_US.UTF-8`로 바꾸면 됨.
- frontend에서 root crash문제
  - 증상1: 파일 존재 체크 메시지까지만 뜨고 실제 ROOT파일 열기 진행되지 않음
  - 증상2: `root -l` 실행시 root자체가 crash남.
  - 증상3: `cling (LLVM option parsing): for the --optimize-regalloc option: may only occur zero or one times!` 메시지를 내고 종료됨.
  - 해결방법: LD_LIBRARY_PATH에 서로 다른 root library가 중복해 적혀있어 충돌난것임. LD_LIBRARY_PATH에서 mamba쪽만 살린 다음 재실행.

