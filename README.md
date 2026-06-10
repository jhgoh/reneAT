# reneAT: RENE data analysis tools
A lightweight production and analysis tools for RENE experiment

RENE실험 데이터 분석을 위하여 RAW데이터로부터 flat ntuple을 생성합니다.
RENE실험의 RAW데이터 형식은 CUPDAQ를 기반으로 하며, FADC와 SADC 파일로 나뉘어 생성됩니다.
데이터 분석의 편의성을 위하여 이를 하나로 합치고, flat ntuple형식으로 변환합니다.

## Flat analysis ntuple production
RAW 데이터로부터 flat ntuple을 생성합니다. 다음 순서로 진행합니다.

- (로그인 할 때마다) hep2026.01 mamba환경 진입
- (한번만) `libRawObj.so` 라이브러리 파일 빌드
- `raw2flat.py` 를 이용해 RAW 파일을 flat ntuple 생성

### Initial setup
먼저 `libRawObj.so`파일을 빌드합니다.
CUPDAQ 라이브러리 중 데이터포맷 부분만 가져와 활용하였습니다.

경희대 환경에서는 mamba를 이용하여 root 및 관련 패키지를 사용합니다.
잘 되지 않으면 아래 Troubleshooting 섹션을 확인 해 보세요.
```bash
mamba activate hep2026.01 ## 로그인 할 때마다.
LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production/RawObjs
make clean
make
```
위 명령어 실행 뒤 `Production` 디렉토리 아래에 `libRawObjs.so`와 `Dict.cc`, 그리고 `Dict_rdict.pcm` 파일이 생성되어 있어야 합니다.

다음으로, 
RAW 디렉토리를 가리키는 링크를 추가하고 PRD파일 생성을 위한 디렉토리를 추가합니다. 
단, 아래 ln 명령어 뒤의 경로는 시스템에 따라 달라질 수 있고, PRD디렉토리는 다른 곳에 만들고 링크를 추가하거나, central PRD디렉토리를 가리키게 할 수도 있습니다. (쓰기 권한 확인 필요)
```bash
cd Production
ln -s /store/cpnr-data/RENE/RAW
mkdir PRD
```


### Production
아래와 같이 production을 진행합니다.
```
mamba activate hep2026.01 ## 로그인 할 때마다.
LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production
./raw2flat.py <RUN_NUMBER> 
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
  - 증상: 파일 존재 체크 메시지까지만 뜨고 실제 ROOT파일 열기 진행되지 않음
  - 추가증상: `root -l` 실행시 root자체가 crash남.
  - 해결방법: LD_LIBRARY_PATH에 두 library가 중복해 적혀있어 충돌난것임. LD_LIBRARY_PATH에서 mamba쪽만 살린 다음 재실행.

