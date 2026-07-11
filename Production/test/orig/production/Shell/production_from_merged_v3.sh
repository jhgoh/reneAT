#!/bin/bash

run=$1 # ex) 000111
subrun=$2 # ex) 1
prev_subrun=$((subrun-1))

pwDir=`pwd`
CodeDir=$pwDir/../Code
DataDir=$3

PRDDir=$DataDir/PRD; mkdir -p $PRDDir

TCBLOG=$DataDir/../../LOG/TCB_$run.log

UseLog=$PRDDir/Run${run}_DLY_THR.log

cat $TCBLOG | grep WJ > $UseLog

cd $CodeDir
run_num=$(echo $run | sed 's/^0*//')

prevLOG=$pwDir/../LOG/log_production_run${run_num}_subrun${prev_subrun}.txt
LOG=$pwDir/../LOG/log_production_run${run_num}_subrun${subrun}.txt

## removed by WJ @ 2026.02.16 #
## updated by WJ @ 2025.01.13 #
#prev_tcbtrgT=0
#tcbtrgC=0
#if [ $subrun -gt 0 ]; then
#	prev_tcbtrgT=$(grep PREV_TCBTRGT ${prevLOG} | awk '{print $2}')
#	tcbtrgC=$(grep TCBTRGC ${prevLOG} | awk '{print $2}')
#fi
###############################

date > $LOG

root -l -b -q production_from_merged_v3.cc\($run_num,$subrun,\"${DataDir}\"\)  >> $LOG 

date >>$LOG

