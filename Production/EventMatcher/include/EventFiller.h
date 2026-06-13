#ifndef EventFiller_H
#define EventFiller_H

#include "RawObjs/EventInfo.hh"
#include "RawObjs/FChannelData.hh"
#include "RawObjs/AChannelData.hh"

#include "TFile.h"
#include "TTree.h"

#include <string>
#include <vector>

class EventFiller {
public:
  struct RunInfo {
    unsigned int runNumber;
    std::vector<int> F_PID, F_DLY, F_THR, F_RL;  // size = nF, per FADC channel
    std::vector<int> S_PID, S_DLY, S_THR, S_GW;  // size = nS, per SADC channel
  };

  EventFiller(const std::string& fName, const RunInfo& info);
  ~EventFiller();

  void Fill(EventInfo* eFADC, EventInfo* eSADC, FChannelData* fCh, AChannelData* aCh);

private:
  TFile* fout_;
  TTree* runTree_;
  TTree* eventTree_;

  RunInfo runInfo_;  // owned copy; .data() pointers used for Run tree branch booking
  int nF_, nS_;

  // Run tree scalar buffers (vectors use runInfo_.*.data() directly)
  unsigned int rb_RunNumber_;
  int rb_nF_, rb_nS_;

  // Event tree buffers
  unsigned int b_TrgNum_;
  int b_EventType_;
  double b_TCBTRGTime_;

  int b_nCH_FADC_;
  int *b_F_PmtID_, *b_F_Triggered_, *b_F_NDP_;
  unsigned short *b_F_THR_;
  double *b_F_WaveStartTime_;
  short *b_F_Pedestal_;
  std::vector<unsigned short> *b_F_Waveform_;  // one vector per FADC channel

  int b_nCH_SADC_;
  int *b_S_PmtID_, *b_S_Triggered_, *b_S_ADC_;
  unsigned short *b_S_THR_;
  double *b_S_WaveStartTime_, *b_S_PeakTime_;
};

#endif
