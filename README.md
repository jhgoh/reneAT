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

```bash
mamba activate hep2026.01 ## 로그인 할 때마다.
LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production/RawObjs
make clean
make
```

`Production` 디렉토리 아래에 `libRawObjs.so`와 `Dict.cc`, 그리고 `Dict_rdict.pcm` 파일이 생성되어 있어야 합니다.

### Production
아래와 같이 production을 진행합니다.
```
mamba activate hep2026.01 ## 로그인 할 때마다.
LANG=en_US.UTF-8 ## LANG=C에서 빌드 문제 생기는 경우가 있었음.

cd Production
./raw2flat.py -r <RUN_NUMBER> 
```

## Troubleshooting
- `LANG=C`일때 라이브러리 로딩 문제: `LANG=en_US.UTF-8`로 바꾸면 됨.
```
Error in cling::AutoLoadingVisitor::InsertIntoAutoLoadingState:
   Missing FileEntry for RawObjs/AbsChannel.hh
   requested to autoload type AbsChannel
```

