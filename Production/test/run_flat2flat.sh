#!/bin/bash
#SBATCH --job-name=flat2flat
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --partition=normal
#SBATCH --mem=2G
#SBATCH --nodelist=suicune

#echo "BEGIN JOB at "`hostname`
echo $1 $2
#date

FIN=$1
FOUT=$2

if [ ! -f $FIN ]; then
    echo "!!! Cannot find input file $FIN..."
    exit
fi

if [ -f $FOUT ]; then
    echo "!!! Output file already exists $FOUT..."
    exit
fi

if [ ! -f flat2flat.py ]; then
    echo "!!! Cannot find converter script flat2flat.py..."
    echo "    PWD=$PWD"
    exit
fi

./flat2flat.py $FIN $FOUT
#./comparePRD.py -kq $FIN $FOUT
#./comparePRD.py -k $FIN $FOUT

#echo "END JOB"
#date
