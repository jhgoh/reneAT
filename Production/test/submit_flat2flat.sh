#!/bin/bash
RUN=$1
SRCDIR=/store/cpnr-data/RENE/PRD
OUTDIR=/store/cpnr-data/RENE/_rePRD_

RUN=`printf %06d $((10#$RUN))`

if [ ! -d $SRCDIR/$RUN ]; then
    echo "!!! Cannot find source directory $SRCDIR/$RUN..."
    exit
fi

if [ -d $OUTDIR/$RUN ]; then
    echo "!!! Output directory already exists $OUTDIR/$RUN..."
    exit
fi

if [ ! -f flat2flat.py ]; then
    echo "!!! Cannot find converter script flat2flat.py..."
    echo "    PWD=$PWD"
    exit
fi

mkdir -p $OUTDIR/$RUN

I=0
find $SRCDIR/$RUN -name '*.root' | while read FIN; do
  FOUT=$OUTDIR/$RUN/`basename $FIN`
  sbatch --job-name=f2f_${RUN}_${I} run_flat2flat.sh $FIN $FOUT
  I=$((I+1))
done

