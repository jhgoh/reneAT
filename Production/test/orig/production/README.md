# Original Production Pipeline

> 이 문서는 [Claude](https://claude.ai) (Anthropic)의 도움을 받아 작성되었습니다.

FADC/SADC RAW 파일을 병합(Merge)하고 PRD ntuple로 변환하는 파이프라인입니다.

## 디렉토리 구조

```
production/
├── setup.sh                          # ROOT 환경 설정 (LCG 또는 mamba)
├── Base/                             # 공유 C++ 클래스 (ChargeSum, SADC, Wave)
├── Code/
│   ├── merge_FADC_SADC.cc            # FADC+SADC 병합 매크로 (로컬용)
│   ├── merge_FADC_SADC_remote.cc     # FADC+SADC 병합 매크로 (배치용, RAWDir 분리)
│   ├── production_from_merged_v3.cc  # Merged → PRD 변환 매크로
│   └── variables_for_production.hh   # 공유 변수 헤더
├── Shell/
│   ├── merge_FADC_SADC_v3.sh             # 로컬 인터랙티브 실행
│   ├── production_from_merged_v3.sh      # 로컬 production 단계 실행
│   ├── merge_FADC_SADC_v3_remote.sh      # 배치 실행 (merge + produce)
│   ├── production_from_merged_v3_remote.sh # 배치 production 단계 실행
│   ├── submit_merge_prd_v3_remote.sh     # SLURM/HTCondor 배치 제출
│   └── run_merge_prd_v3_remote.sh        # SLURM 잡 래퍼
├── RAW    -> /path/to/RAW            # 심링크: RAW 데이터 입력
├── PRD    -> /path/to/PRD            # 심링크: PRD 출력
├── DAQLOG -> /path/to/DAQLOG        # 심링크: TCB 로그
└── LOG/                              # 런타임 로그 (git 추적 제외)
```

## 파이프라인 흐름

```
RAW/
├── FADC_<RUN>.root.<SUBRUN>   ─┐
└── SADC_<RUN>.root.<SUBRUN>   ─┴─► merge_FADC_SADC*.cc ─► Merged/ ─► production_from_merged_v3.cc ─► PRD/
```

서브런 단위로 순차 처리하며, 한 서브런의 merge→produce가 완료되면 다음 서브런으로 진행합니다.
SADC는 서브런 경계가 FADC와 다를 수 있어 병합 매크로가 양쪽의 트리거 번호를 맞춰가며 처리합니다.

## 초기 설정

### 1. libRawObjs.so 빌드

`Code/` 매크로는 RawObjs 라이브러리에 의존합니다. 배치 시스템에서 실행하기 전에 해당 시스템에서 한 번 빌드합니다.
빌드 방법은 [최상위 README](../../../../README.md#1-라이브러리-빌드)를 참고하세요.

> **주의**: `libRawObjs.so`는 실행 환경과 동일한 ROOT 버전으로 빌드해야 합니다.
> `setup.sh`가 LCG를 사용하는 사이트라면 LCG ROOT로, mamba를 사용하는 사이트라면 mamba ROOT로 빌드합니다.

### 2. 심링크 설정

`production/` 디렉토리 아래에 다음 세 심링크를 만듭니다.

| 심링크 | 용도 |
|--------|------|
| `RAW`    | FADC/SADC raw 입력 데이터 |
| `PRD`    | PRD ntuple 출력 |
| `DAQLOG` | TCB 로그 (trigger time 참조) |

```bash
cd Production/test/orig/production
ln -s /store/cpnr-data/RENE/RAW    RAW
ln -s /store/cpnr-data/RENE/_rePRD_ PRD
ln -s /store/cpnr-data/RENE/DAQLOG  DAQLOG
```

경로는 사이트에 따라 다릅니다.

## 실행 방법

### 로컬 인터랙티브 실행

```bash
cd production/Shell
./merge_FADC_SADC_v3.sh
# 프롬프트에서 런 번호 입력 (예: 004000)
```

### 배치 제출 (SLURM / HTCondor 자동 감지)

```bash
cd production/Shell
./submit_merge_prd_v3_remote.sh <RUN>
# 예) ./submit_merge_prd_v3_remote.sh 004000
```

SLURM이 있으면 `sbatch`, HTCondor가 있으면 `condor_submit`으로 자동 선택됩니다.
JDL 및 로그 파일은 `production/LOG/` 에 저장됩니다.

#### SLURM 잡 확인

```bash
squeue -u $USER
tail -f ../LOG/slurm_merge_prd_<RUN>_<JOBID>.out
```

#### HTCondor 잡 확인

```bash
condor_q
tail -f ../LOG/condor_merge_prd_<RUN>.out
```

## setup.sh

`merge_FADC_SADC_v3_remote.sh` 시작 시 자동으로 `source`됩니다.
CVMFS LCG를 우선 시도하고, 없으면 mamba로 폴백합니다.

| 환경 | 조건 | ROOT 버전 |
|------|------|-----------|
| CVMFS LCG 106 | `/cvmfs/sft.cern.ch` 존재 시 | 6.32.x |
| mamba hep2026.01 | `mamba` 명령 존재 시 | 6.28.x |

## 지원 OS (LCG)

| OS | LCG 플랫폼 |
|----|-----------|
| Ubuntu 22.04 | `x86_64-ubuntu2204-gcc11-opt` |
| Ubuntu 20.04 | `x86_64-ubuntu2004-gcc9-opt` |
| RHEL/AlmaLinux/Rocky 9.x | `x86_64-el9-gcc13-opt` |
| RHEL/CentOS/AlmaLinux/Rocky 8.x | `x86_64-centos8-gcc11-opt` |
