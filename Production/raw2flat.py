#!/usr/bin/env python
import sys, os
import argparse
parser = argparse.ArgumentParser(description=f'{sys.argv[0]}: RENE RAW to Flat Production file')
parser.add_argument('runNum', type=int, help='Run number')
#parser.add_argument('runNum', type=int, nargs='+', help='Run number')
parser.add_argument('-v', '--verbose', action=argparse.BooleanOptionalAction, default=True)
parser.add_argument('-p', '--progress', action=argparse.BooleanOptionalAction, default=True)
args = parser.parse_args()

runNum = args.runNum

def printInfo(line):
    if not args.verbose: return
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
printInfo(f"Output directory {outDir} is writable. Creating output directory...")
os.makedirs(outDir)

## Check the file exists
rawDir = f'RAW/{runNum:06d}'
if not os.path.isdir(rawDir):
    print(f"ERROR: Cannot find RAW file directory with run number = {runNum}")
    sys.exit(1)
printInfo(f"Input directory {rawDir} exists.")

## Collect input files
from glob import glob
subruns = []
fNamesFADC, fNamesSADC = {}, {}
missingSADCFiles = []
for fNameFADC in glob(f"{rawDir}/FADC_{runNum:06d}.root.*"):
    subrun = fNameFADC.rsplit('.',1)[-1]
    fNameSADC = f"{rawDir}/SADC_{runNum:06d}.root.{subrun}"
    if not os.path.exists(fNameSADC):
        print(f"ERROR: Missing SADC subrun file, subrun={subrun}")
        missingSADCFiles.append(fNameSADC)
        fNameSADC = None
    subruns.append(subrun)
    fNamesFADC[subrun] = fNameFADC
    fNamesSADC[subrun] = fNameSADC
if len(missingSADCFiles) > 0:
    sys.exit(1)
subruns.sort()
fNamesFADC = [fNamesFADC[subrun] for subrun in subruns]
fNamesSADC = [fNamesSADC[subrun] for subrun in subruns]

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
    if fFADC == None or fFADC.IsZombie():
        print(f"ERROR: Invalid FADC file {fNameFADC}")
        brokenFiles.append(fNameFADC)
    else:
        tFADC = fFADC.Get("AbsEvent")
        if tFADC == None:
            print(f"ERROR: Invalid FADC tree {fNameFADC}")
            brokenFiles.append(fNameFADC)
    if fSADC == None or fSADC.IsZombie():
        print(f"ERROR: Invalid SADC file {fNameSADC}")
        brokenFiles.append(fNameSADC)
    else:
        tSADC = fSADC.Get("AbsEvent")
        if tSADC == None:
            print(f"ERROR: Invalid SADC tree {fNameSADC}")
            brokenFiles.append(fNameSADC)
if len(brokenFiles) > 0:
    print(f"ERROR: There are broken files. Stop.")
    sys.exit(2)
else:
    fFADC = fSADC = tFADC = tSADC = None
    printInfo(f"Files are OK subruns={len(subruns)}")

if len(fNamesFADC) == 0:
    print(f"ERROR: No files to process.")
    sys.exit(2)

## Book output file and tree
sys.path.append("python")
from runinfo import RunInfo
from logreader import TCBLogReader

class OutTreeFile:
    def __init__(self, fName, runInfo):
        self.runInfo = runInfo
        self.nF = runInfo.nF[0]
        self.nS = runInfo.nS[0]

        self._f = ROOT.TFile(fName, "RECREATE")

        ## RunInfo
        self.rt = ROOT.TTree("Run", "Run")
        self.rt.Branch("RunNumber", runInfo.runNumber, "RunNumber/i")

        self.rt.Branch("nF", runInfo.nF, "nF/I")
        self.rt.Branch("F_PmtID", runInfo.F_PID, "F_PmtID[nF]/I")
        self.rt.Branch("F_DLY"  , runInfo.F_DLY, "F_DLY[nF]/I"  )
        self.rt.Branch("F_THR"  , runInfo.F_THR, "F_THR[nF]/I"  )
        self.rt.Branch("F_RL"   , runInfo.F_RL , "F_RL[nF]/I"   )

        self.rt.Branch("nS", runInfo.nS, "nS/I")
        self.rt.Branch("S_PmtID", runInfo.S_PID, "S_PmtID[nS]/I")
        self.rt.Branch("S_DLY"  , runInfo.S_DLY, "S_DLY[nS]/I"  )
        self.rt.Branch("S_THR"  , runInfo.S_THR, "S_THR[nS]/I"  )
        self.rt.Branch("S_GW"   , runInfo.S_GW , "S_GW[nS]/I"   )

        self.rt.Fill()

        ## EventInfo
        self._t = ROOT.TTree("Event", "Event")

        self.b_TrgNum = np.zeros(1, dtype=np.uint32)
        self.b_EventType = np.zeros(1, dtype=np.uint32)
        self.b_TCBTRGTime = np.zeros(1, dtype=np.float64)#dtype=np.uint64)

        self._t.Branch("TrgNum", self.b_TrgNum, "TrgNum/i")
        self._t.Branch("EventType", self.b_EventType, "EventType/i")
        self._t.Branch("TCBTRGTime", self.b_TCBTRGTime, "TCBTRGTime/D") #"TCBTRGTime/i")

        ## FADC
        self.b_nCH_FADC        = np.array([self.nF], dtype=np.int32)
        self.b_F_PmtID         = np.zeros(self.nF, dtype=np.int32)
        self.b_F_THR           = np.zeros(self.nF, dtype=np.uint16)
        self.b_F_Triggered     = np.zeros(self.nF, dtype=np.int32)
        self.b_F_WaveStartTime = np.zeros(self.nF, dtype=np.float64)
        self.b_F_Pedestal      = np.zeros(self.nF, dtype=np.int16)
        self.b_F_NDP           = np.zeros(self.nF, dtype=np.int32)

        self._t.Branch("nCH_FADC"       , self.b_nCH_FADC       , "nCH_FADC/I")
        self._t.Branch("F_PmtID"        , self.b_F_PmtID        , "F_PmtID[nCH_FADC]/I")
        self._t.Branch("F_THR"          , self.b_F_THR          , "F_THR[nCH_FADC]/s")
        self._t.Branch("F_Triggered"    , self.b_F_Triggered    , "F_Triggered[nCH_FADC]/I")
        self._t.Branch("F_WaveStartTime", self.b_F_WaveStartTime, "F_WaveStartTime[nCH_FADC]/D")
        self._t.Branch("F_Pedestal"     , self.b_F_Pedestal     , "F_Pedestal[nCH_FADC]/S")
        self._t.Branch("F_NDP"          , self.b_F_NDP          , "F_NDP[nCH_FADC]/I")

        self.bs_F_Waveform = [ROOT.std.vector('unsigned short')() for i in range(self.nF)]
        for iCH, b in enumerate(self.bs_F_Waveform):
            self._t.Branch(f"F_Waveform_{iCH}", b)

        ## SADC
        self.b_nCH_SADC        = np.array([self.nS], dtype=np.int32)
        self.b_S_PmtID         = np.zeros(self.nS, dtype=np.int32)
        self.b_S_THR           = np.zeros(self.nS, dtype=np.uint16)
        self.b_S_Triggered     = np.zeros(self.nS, dtype=np.int32)
        self.b_S_WaveStartTime = np.zeros(self.nS, dtype=np.float64)
        self.b_S_PeakTime      = np.zeros(self.nS, dtype=np.float64)
        self.b_S_ADC           = np.zeros(self.nS, dtype=np.int32)

        self._t.Branch("nCH_SADC"       , self.b_nCH_SADC       , "nCH_SADC/I")
        self._t.Branch("S_PmtID"        , self.b_S_PmtID        , "S_PmtID[nCH_SADC]/I")
        self._t.Branch("S_THR"          , self.b_S_THR          , "S_THR[nCH_SADC]/s")
        self._t.Branch("S_Triggered"    , self.b_S_Triggered    , "S_Triggered[nCH_SADC]/I")
        self._t.Branch("S_WaveStartTime", self.b_S_WaveStartTime, "S_WaveStartTime[nCH_SADC]/D")
        self._t.Branch("S_PeakTime"     , self.b_S_PeakTime     , "S_PeakTime[nCH_SADC]/D")
        self._t.Branch("S_ADC"          , self.b_S_ADC          , "S_ADC[nCH_SADC]/I")

    def Fill(self, tFADC, tSADC):
        eFADC, eSADC = tFADC.EventInfo, tSADC.EventInfo
        tcbTimeFADC = eFADC.GetTCBTriggerTime()
        tcbTimeSADC = eSADC.GetTCBTriggerTime()
        
        self.b_TrgNum[0] = eFADC.GetTriggerNumber()
        self.b_TCBTRGTime[0] = tcbTimeFADC

        fCH = tFADC.FChannelData
        aCH = tSADC.AChannelData

        self.b_F_THR[:] = runInfo.F_THR
        self.b_F_WaveStartTime[:] = tcbTimeFADC - runInfo.F_DLY
        hasFADCOverThr = 0
        for iCH in range(self.nF):
            ch = fCH.Get(iCH)
            self.b_F_PmtID[iCH] = ch.GetID()
            self.b_F_Triggered[iCH] = ch.GetBit()
            self.b_F_Pedestal[iCH] = ch.GetPedestal()
            self.b_F_NDP[iCH] = ch.GetSize()

            waveform = np.frombuffer(ch.GetWaveform(), dtype=np.uint16, count=ch.GetSize())
            self.bs_F_Waveform[iCH].assign(waveform)
            hasFADCOverThr += np.any(waveform > self.b_F_Pedestal[iCH] + self.b_F_THR[iCH])
        self.b_EventType[0] = 1 if hasFADCOverThr > 0 else 0

        self.b_S_THR[:] = runInfo.S_THR
        self.b_S_WaveStartTime[:] = tcbTimeSADC - runInfo.S_DLY
        for iCH in range(self.nS):
            ch = aCH.Get(iCH)
            self.b_S_PmtID[iCH] = ch.GetID()
            self.b_S_Triggered[iCH] = ch.GetBit()
            self.b_S_ADC[iCH] = ch.GetADC()
        
            self.b_S_PeakTime[iCH] = ch.GetTime()
        self.b_S_PeakTime -= self.b_S_WaveStartTime
        self.b_S_PeakTime[self.b_S_PeakTime < 0] = -99
        hasSADCOverThr = np.any(self.b_S_ADC > self.b_S_THR)
        if hasSADCOverThr > 0:
            self.b_EventType[0] += 2

        self._t.Fill()

    def __del__(self):
        if self._f != None:
            self._f.cd()
            self._t.Write()
            self._f.Write()
            self._f.Close()

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
                if iSubrunSADC >= len(subruns): break
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

        if isToSkip: continue

        ## Now we are ready to fill up the event
        if isMatched:
            #tSADC.GetEntry(iEntrySADC) ## already done in the loop
            nEvents += 1
            out.Fill(tFADC, tSADC)

    del out
