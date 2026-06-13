#!/usr/bin/env python
import sys
import os
import argparse
import time
from glob import glob

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{sys.argv[0]}: RENE RAW to Flat Production file (C++ backend)')
    parser.add_argument('runNum', type=int, help='Run number')
    parser.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    runNum = args.runNum

    def printInfo(line):
        if not args.verbose:
            return
        print("DEBUG:", line)

    ## Check the output directory already exists
    outDir = f'PRD/{runNum:06d}'
    if os.path.isdir(outDir):
        print(f"ERROR: Ouput directory {outDir} already exists...")
        print(f"       Please remove the target directory and retry this script.")
        sys.exit(1)
    if not os.access('PRD', os.W_OK):
        print(f"ERROR: Output directory {outDir} is not writable...")
        print(f"       Please check write permission of the target directory.")
        sys.exit(1)
    printInfo(f"Output directory {outDir} is writable.")

    ## Check the file exists
    rawDir = f'RAW/{runNum:06d}'
    if not os.path.isdir(rawDir):
        print(f"ERROR: Cannot find RAW file directory with run number = {runNum}")
        sys.exit(1)
    printInfo(f"Input directory {rawDir} exists.")

    ## Collect input files
    subruns = []
    fNamesFADC, fNamesSADC = {}, {}
    missingSADCFiles = []
    for fNameFADC in glob(f"{rawDir}/FADC_{runNum:06d}.root.*"):
        subrun = fNameFADC.rsplit('.', 1)[-1]
        fNameSADC = f"{rawDir}/SADC_{runNum:06d}.root.{subrun}"
        if not os.path.exists(fNameSADC):
            print(f"ERROR: Missing SADC subrun file, subrun={subrun}")
            missingSADCFiles.append(fNameSADC)
            fNameSADC = None
        subruns.append(subrun)
        fNamesFADC[subrun] = fNameFADC
        fNamesSADC[subrun] = fNameSADC
    if missingSADCFiles:
        sys.exit(1)
    subruns.sort()
    fNamesFADC = [fNamesFADC[subrun] for subrun in subruns]
    fNamesSADC = [fNamesSADC[subrun] for subrun in subruns]

    if not fNamesFADC:
        print(f"ERROR: No files to process.")
        sys.exit(2)

    ## ROOT and numpy are imported here to avoid slow startup on early exit above
    import ROOT
    ROOT.gSystem.Load("RawObjs/libRawObjs.so")
    ROOT.gInterpreter.AddIncludePath("RawObjs/include")
    ROOT.gInterpreter.ProcessLine('#include "RawObjs/EventInfo.hh"')

    ## Check file status. Stop process if there's any problem
    brokenFiles = []
    for subrun, fNameFADC, fNameSADC in zip(subruns, fNamesFADC, fNamesSADC):
        fFADC = ROOT.TFile(fNameFADC)
        fSADC = ROOT.TFile(fNameSADC)
        if fFADC == None or fFADC.IsZombie():  # == None intentional: ROOT object comparison
            print(f"ERROR: Invalid FADC file {fNameFADC}")
            brokenFiles.append(fNameFADC)
        else:
            tFADC = fFADC.Get("AbsEvent")
            if tFADC == None:  # == None intentional: ROOT object comparison
                print(f"ERROR: Invalid FADC tree {fNameFADC}")
                brokenFiles.append(fNameFADC)
        if fSADC == None or fSADC.IsZombie():  # == None intentional: ROOT object comparison
            print(f"ERROR: Invalid SADC file {fNameSADC}")
            brokenFiles.append(fNameSADC)
        else:
            tSADC = fSADC.Get("AbsEvent")
            if tSADC == None:  # == None intentional: ROOT object comparison
                print(f"ERROR: Invalid SADC tree {fNameSADC}")
                brokenFiles.append(fNameSADC)
    if brokenFiles:
        print(f"ERROR: There are broken files. Stop.")
        sys.exit(2)
    else:
        fFADC = fSADC = tFADC = tSADC = None
        printInfo(f"Files are OK subruns={len(subruns)}")

    printInfo(f"Creating output directory {outDir}...")
    os.makedirs(outDir)

    ## Local imports must come after sys.path.append
    sys.path.append("python")
    from runinfo import RunInfo
    from logreader import TCBLogReader

    ## Load C++ EventMatcher library
    ROOT.gSystem.Load("EventMatcher/libEventMatcher.so")
    ROOT.gInterpreter.AddIncludePath("EventMatcher/include")
    ROOT.gInterpreter.ProcessLine('#include "EventMatcher.h"')

    ## Extract run information from the log file (reuse existing Python logreader)
    runInfo = RunInfo(runNum, *TCBLogReader(runNum).ExtractWJ())

    ## Convert Python RunInfo to C++ EventFiller::RunInfo
    runInfo_cpp = ROOT.EventFiller.RunInfo()
    runInfo_cpp.Set(int(runInfo.runNumber[0]), runInfo.GetDict())

    ## Build SADC filename list as std::vector<string> for C++ EventMatcher
    sadcVec = ROOT.std.vector('string')()
    for fName in fNamesSADC:
        sadcVec.push_back(fName)

    ## Run C++ event matching and tree filling
    matcher = ROOT.EventMatcher(sadcVec, args.verbose)
    tTotal = 0.0
    for subrun, fNameFADC in zip(subruns, fNamesFADC):
        fNameOut = f"{outDir}/PRD_{runNum:06d}.{subrun}.root"
        t0 = time.perf_counter()
        nMatched = matcher.Process(fNameOut, subrun, fNameFADC, runInfo_cpp)
        dt = time.perf_counter() - t0
        tTotal += dt
        print(f"subrun={subrun}  matched={nMatched}  time={dt:.1f}s")
    print(f"Total: {len(subruns)} subruns  time={tTotal:.1f}s")
