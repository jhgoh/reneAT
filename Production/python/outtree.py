#!/usr/bin/env python
import numpy as np
import ROOT

# Book output file and tree
class OutTreeFile:
    def __init__(self, fName, runInfo):
        self.runInfo = runInfo
        self.nF = runInfo.nF[0]
        self.nS = runInfo.nS[0]

        ## ZSTD at LV4 seem to be reasonable (-10% size, +20% in time)
        #self._f = ROOT.TFile(fName, "RECREATE")
        self._f = ROOT.TFile(fName, "RECREATE", "", ROOT.kZSTD)
        self._f.SetCompressionLevel(4)

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
        self.b_EventType = np.zeros(1, dtype=np.int32)
        self.b_TCBTRGTime = np.zeros(1, dtype=np.float64)#dtype=np.uint64)

        self._t.Branch("TrgNum", self.b_TrgNum, "TrgNum/i")
        self._t.Branch("EventType", self.b_EventType, "EventType/I")
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
        trgTimeFADC = eFADC.GetTriggerTime()
        trgTimeSADC = eSADC.GetTriggerTime()
        tcbTimeFADC = eFADC.GetTCBTriggerTime()
        tcbTimeSADC = eSADC.GetTCBTriggerTime()
        
        self.b_TrgNum[0] = eFADC.GetTriggerNumber()
        self.b_TCBTRGTime[0] = tcbTimeFADC

        fCH = tFADC.FChannelData
        aCH = tSADC.AChannelData

        self.b_F_THR[:] = self.runInfo.F_THR
        self.b_F_WaveStartTime[:] = trgTimeFADC - self.runInfo.F_DLY
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

        self.b_S_THR[:] = self.runInfo.S_THR
        self.b_S_WaveStartTime[:] = trgTimeSADC - self.runInfo.S_DLY
        for iCH in range(self.nS):
            ch = aCH.Get(iCH)
            self.b_S_PmtID[iCH] = ch.GetID()
            self.b_S_Triggered[iCH] = ch.GetBit()
            self.b_S_ADC[iCH] = ch.GetADC()
        
            self.b_S_PeakTime[iCH] = ch.GetTime() - (tcbTimeSADC - self.runInfo.S_DLY[iCH])
        #self.b_S_PeakTime[self.b_S_PeakTime < 0] = -99
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

