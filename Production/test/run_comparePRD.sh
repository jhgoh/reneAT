#!/bin/bash
#SBATCH --job-name=comparePRD
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --partition=normal
#SBATCH --mem=10G
#SBATCH --nodelist=suicune

RUN=$1
DIR1=/store/cpnr-data/RENE/PRD
DIR2=/store/cpnr-data/RENE/_rePRD_

RUN=`printf %06d $((10#$RUN))`

HASERR=0
find $DIR1/$RUN -name '*.root' | while read FIN; do
  F1=$DIR1/$RUN/PRD/`basename $FIN`
  F2=$DIR2/$RUN/`basename $FIN`
  ls $F1 $F2
  sleep 1
  ./comparePRD.py -kq $F1 $F2 || HASERR=$((HASERR+1))
done

echo "DONE. $HASERR"
