#!/bin/bash

run=$1  # ex) 000111

shellDir=$(dirname $(realpath $0))
prodDir=$shellDir/..
CodeDir=$prodDir/Code
logDir=$prodDir/LOG; mkdir -p $logDir

libDir=$(realpath $shellDir/../../../../RawObjs)
if [ ! -f $libDir/libRawObjs.so ]; then
    echo "!!! libRawObjs.so not found at $libDir" >&2
    echo "!!! Run: cd $libDir && make" >&2
    exit 1
fi

source $prodDir/setup.sh || exit 1

export LD_LIBRARY_PATH=$libDir:$LD_LIBRARY_PATH
export ROOT_INCLUDE_PATH=$libDir/include:$ROOT_INCLUDE_PATH

RawDir=$prodDir/RAW/$run
DataDir=$prodDir/PRD/$run
mkdir -p $DataDir

MergedDir=$DataDir/Merged; mkdir -p $MergedDir
PNGDir=$DataDir/PNG; mkdir -p $PNGDir

maxsubrun=`ls -l $RawDir/ | grep root | grep FADC | grep -v grep | wc -l`
maxsubrun=$(( $maxsubrun - 1 ))
echo "Max subrun # = "$maxsubrun

run_num=$(echo $run | sed 's/^0*//')

fadcSubrun=0
sadcSubrun=0
sadcEvent=0
sadcTrgnum=0

while [ 1 ]; do

    cd $CodeDir

    if [ $fadcSubrun -gt $maxsubrun ] || [ $sadcSubrun -gt $maxsubrun ]; then
		echo " Merging + Producing DONE "
        break
    fi

    LOG=$logDir/log_merge_FADC_SADC_run${run_num}_subrun${fadcSubrun}.txt
    RealtimeLOG=$logDir/log_merge_prod_run${run_num}_subrun${fadcSubrun}.txt

    date > $RealtimeLOG

    # Merging
    date > $LOG

	while [ 1 ]
	do
		flag_zombie=0
    	echo "["`date`"] Merging ... "
		root -l -b \
			-e "gSystem->AddIncludePath(\"-I${libDir}/include\"); gSystem->Load(\"${libDir}/libRawObjs.so\");" \
			-q merge_FADC_SADC_remote.cc\($run_num,$maxsubrun,$fadcSubrun,$sadcSubrun,$sadcEvent,$sadcTrgnum,\"$RawDir\",\"$DataDir\"\) >> $LOG

		if [ $? -eq 0 ]; then
			break
		fi

		((flag_zombie++))

		if [ $flag_zombie -gt 5 ]; then
            echo " ZOMBIE FILE DETECTED "
			exit
		fi

		echo " Zombie file check: "$flag_zombie" / 5 -> sleep 1m "
		sleep 1m
	done

    date >> $LOG
    echo " Merging Done : Run"$run_num"."$fadcSubrun >> $RealtimeLOG

    # Producing
    cd $shellDir
    echo "["`date`"] Producing ... "
    ./production_from_merged_v3_remote.sh $run $fadcSubrun $DataDir

    echo " Producing Done : Run"$run_num"."$fadcSubrun >> $RealtimeLOG
    date >> $RealtimeLOG

    fadcSubrun=$(grep "^final FADC "              $LOG | tail -1 | awk '{print $4}')
    sadcSubrun=$(grep "^final SADC "              $LOG | tail -1 | awk '{print $4}')
    sadcEvent=$(grep  "^final SADC_evt "          $LOG | tail -1 | awk '{print $4}')
    sadcTrgnum=$(grep "^final before_SADC_trgnum" $LOG | tail -1 | awk '{print $4}')

done
