#!/bin/bash

run=$1 # ex) 000111
subrun=$2 # ex) 1
prev_subrun=$((subrun-1))

shellDir=$(dirname $(realpath $0))
prodDir=$shellDir/..
CodeDir=$prodDir/Code
DataDir=$3

libDir=$(realpath $shellDir/../../../../RawObjs)

source $prodDir/setup.sh || exit 1

export LD_LIBRARY_PATH=$libDir:$LD_LIBRARY_PATH
export ROOT_INCLUDE_PATH=$libDir/include:$ROOT_INCLUDE_PATH

logDir=$prodDir/LOG; mkdir -p $logDir
PRDDir=$DataDir/PRD; mkdir -p $PRDDir

TCBLOG=$prodDir/DAQLOG/TCB/TCB_$run.log.gz

UseLog=$PRDDir/Run${run}_DLY_THR.log

zcat $TCBLOG | grep WJ > $UseLog

cd $CodeDir
run_num=$(echo $run | sed 's/^0*//')

prevLOG=$logDir/log_production_run${run_num}_subrun${prev_subrun}.txt
LOG=$logDir/log_production_run${run_num}_subrun${subrun}.txt

date > $LOG

root -l -b \
    -e "gSystem->AddIncludePath(\"-I${libDir}/include\"); gSystem->Load(\"${libDir}/libRawObjs.so\");" \
    -q production_from_merged_v3.cc\($run_num,$subrun,\"${DataDir}\"\) >> $LOG

date >>$LOG
