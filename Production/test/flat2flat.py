#!/usr/bin/env python
import sys
import os
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{sys.argv[0]}: Rewrite flat tree with higher compression level')
    parser.add_argument('ifName', type=str, help='Input File Name')
    parser.add_argument('ofName', type=str, help='Output File Name')
    parser.add_argument('-c', '--compression-level', type=int, default=4)
    parser.add_argument('--drop-channels', default='2,3', help="Comma-separated FADC channel indices to drop (default: 2,3)")
    parser.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    if not os.path.exists(args.ifName):
        print(f"ERROR: Cannot find input file, \"{args.ifName}\"...")
        sys.exit(1)
    if os.path.exists(args.ofName):
        print(f"ERROR: Output file \"{args.ofName}\" already exists...")
        sys.exit(1)

    import ROOT
    fin = ROOT.TFile(args.ifName)
    t = fin.Get("Event")
    for ch in args.drop_channels.split(','):
        if not ch.isnumeric(): continue
        ch = int(ch)
        t.SetBranchStatus(f"F_Waveform_{ch}", 0)

    fout = ROOT.TFile(args.ofName, "RECREATE", "", ROOT.kZSTD)
    fout.SetCompressionLevel(args.compression_level)

    t = t.CloneTree()
    fout.cd()
    t.SetDirectory(fout)
    t.Write()
    fout.Close()
