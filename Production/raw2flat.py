#!/usr/bin/env python
import sys
import os
import argparse
from glob import glob

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{sys.argv[0]}: RENE RAW to Flat Production file')
    parser.add_argument('runNum', type=int, help='Run number')
    #parser.add_argument('runNum', type=int, nargs='+', help='Run number')
    parser.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('-p', '--progress', action=argparse.BooleanOptionalAction, default=True)
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
    import numpy as np
    import ROOT
    ROOT.gSystem.Load("RawObjs/libRawObjs.so")
    ROOT.gInterpreter.AddIncludePath("RawObjs/include")
    ROOT.gInterpreter.ProcessLine('#include "RawObjs/EventInfo.hh"')

    ## Check file status. Stop process if there's any problem
    brokenFiles = []
    for subrun, fNameFADC, fNameSADC in zip(subruns, fNamesFADC, fNamesSADC):
        ## Try to open files
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
    from outtree import OutTreeFile

    ## Start merging trees based on the trigger number.
    ## Note that the FADC and SADC stores triggered events separaetely,
    ## therefore same triggered event can be stored in different subruns.
    if args.progress:
        from tqdm import tqdm
    else:
        def tqdm(line, **kwargs):
            return line

    ## Extract run information from the log file
    runInfo = RunInfo(runNum, *TCBLogReader(runNum).ExtractWJ())

    iSubrunSADC, iEntrySADC = 0, 0
    fNameSADC = fNamesSADC[iSubrunSADC]
    fSADC = ROOT.TFile(fNameSADC)
    tSADC = fSADC.Get("AbsEvent")
    for subrun, fNameFADC in zip(subruns, fNamesFADC):
        ## Prepare output file
        out = OutTreeFile(f"{outDir}/PRD_{runNum:06d}.{subrun}.root", runInfo)

        ## Read the FADC tree
        fFADC = ROOT.TFile(fNameFADC)
        tFADC = fFADC.Get("AbsEvent")
        nEvents = 0
        for eFADC in tqdm(tFADC, total=tFADC.GetEntries(), desc=f"Processing subrun={subrun}"):
            trgNumFADC = eFADC.EventInfo.GetTriggerNumber()
            tcbTimeFADC = eFADC.EventInfo.GetTCBTriggerTime()

            ## Find matching SADC event, start scanning from the previous trial event
            isMatched, isToSkip = False, False
            while True:
                ## Proceed to next file if the SADC file is already consumed up.
                if iEntrySADC >= tSADC.GetEntries():
                    iSubrunSADC += 1
                    if iSubrunSADC >= len(subruns):
                        break
                    fNameSADC = fNamesSADC[iSubrunSADC]
                    fSADC = ROOT.TFile(fNameSADC)
                    tSADC = fSADC.Get("AbsEvent")
                    iEntrySADC = 0

                ## Load the SADC event
                tSADC.GetEntry(iEntrySADC)
                trgNumSADC = tSADC.EventInfo.GetTriggerNumber()
                tcbTimeSADC = tSADC.EventInfo.GetTCBTriggerTime()

                ## Skip the FADC event if next one already came
                if trgNumSADC > trgNumFADC:
                    isToSkip = True
                    break
                elif trgNumSADC == trgNumFADC:
                    isMatched = True
                    iEntrySADC += 1
                    break

                iEntrySADC += 1

            if isToSkip:
                continue

            ## Now we are ready to fill up the event
            if isMatched:
                #tSADC.GetEntry(iEntrySADC) ## already done in the loop
                nEvents += 1
                out.Fill(tFADC, tSADC)

        del out
