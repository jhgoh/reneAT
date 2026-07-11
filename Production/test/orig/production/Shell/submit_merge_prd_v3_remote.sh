#!/bin/bash
run=$1
run=$(printf %06d $((10#$run)))

pwDir=$(dirname $(realpath $0))
prodDir=$pwDir/..
logDir=$prodDir/LOG
mkdir -p $logDir

if [ ! -d $prodDir/RAW/$run ]; then
    echo "!!! Cannot find RAW directory $prodDir/RAW/$run"
    exit 1
fi

if command -v sbatch &>/dev/null; then
    sbatch --job-name=merge_prd_${run} \
           --output=$logDir/slurm_merge_prd_${run}_%j.out \
           --error=$logDir/slurm_merge_prd_${run}_%j.err \
           --export=ALL,SHELLDIR=$pwDir \
           $pwDir/run_merge_prd_v3_remote.sh $run

elif command -v condor_submit &>/dev/null; then
    jdlFile=$logDir/condor_merge_prd_${run}.jdl
    cat > $jdlFile << EOF
executable            = $pwDir/merge_FADC_SADC_v3_remote.sh
arguments             = $run
output                = $logDir/condor_merge_prd_${run}.out
error                 = $logDir/condor_merge_prd_${run}.err
log                   = $logDir/condor_merge_prd_${run}.log
request_memory        = 4096
should_transfer_files = NO
queue
EOF
    condor_submit $jdlFile

else
    echo "!!! No batch system found (sbatch or condor_submit)"
    exit 1
fi
