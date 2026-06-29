#include "EventFiller.h"
#include "RawObjs/FChannel.hh"
#include "RawObjs/AChannel.hh"

#include <sstream>

EventFiller::EventFiller(const std::string& fName, const RunInfo& runInfo)
  : runInfo_(runInfo)
{
  nF_ = runInfo_.F_PID.size();
  nS_ = runInfo_.S_PID.size();

  // ZSTD level 4: ~-10% size, ~+20% time vs default -- matches Python OutTreeFile
  fout_ = new TFile(fName.c_str(), "RECREATE", "",
                    ROOT::CompressionSettings(ROOT::kZSTD, 4));

  fout_->cd();

  // --- Event tree ---
  b_F_PmtID_         = new int[nF_];
  b_F_Triggered_     = new int[nF_];
  b_F_NDP_           = new int[nF_];
  b_F_THR_           = new unsigned short[nF_];
  b_F_WaveStartTime_ = new double[nF_];
  b_F_Pedestal_      = new short[nF_];
  b_F_Waveform_      = new std::vector<unsigned short>[nF_];

  b_S_PmtID_         = new int[nS_];
  b_S_Triggered_     = new int[nS_];
  b_S_ADC_           = new int[nS_];
  b_S_THR_           = new unsigned short[nS_];
  b_S_WaveStartTime_ = new double[nS_];
  b_S_PeakTime_      = new double[nS_];

  b_nCH_FADC_ = nF_;
  b_nCH_SADC_ = nS_;

  eventTree_ = new TTree("Event", "Event");
  eventTree_->Branch("TrgNum",           &b_TrgNum_,           "TrgNum/i");
  eventTree_->Branch("EventType",        &b_EventType_,        "EventType/I");
  eventTree_->Branch("TCBTRGTime",       &b_TCBTRGTime_,       "TCBTRGTime/D");

  eventTree_->Branch("nCH_FADC",         &b_nCH_FADC_,         "nCH_FADC/I");
  eventTree_->Branch("F_PmtID",          b_F_PmtID_,           "F_PmtID[nCH_FADC]/I");
  eventTree_->Branch("F_THR",            b_F_THR_,             "F_THR[nCH_FADC]/s");
  eventTree_->Branch("F_Triggered",      b_F_Triggered_,       "F_Triggered[nCH_FADC]/I");
  eventTree_->Branch("F_WaveStartTime",  b_F_WaveStartTime_,   "F_WaveStartTime[nCH_FADC]/D");
  eventTree_->Branch("F_Pedestal",       b_F_Pedestal_,        "F_Pedestal[nCH_FADC]/S");
  eventTree_->Branch("F_NDP",            b_F_NDP_,             "F_NDP[nCH_FADC]/I");
  for ( int iCH=0; iCH<nF_; ++iCH ) {
    std::ostringstream bName;
    bName << "F_Waveform_" << iCH;
    eventTree_->Branch(bName.str().c_str(), &b_F_Waveform_[iCH]);
  }

  eventTree_->Branch("nCH_SADC",         &b_nCH_SADC_,         "nCH_SADC/I");
  eventTree_->Branch("S_PmtID",          b_S_PmtID_,           "S_PmtID[nCH_SADC]/I");
  eventTree_->Branch("S_THR",            b_S_THR_,             "S_THR[nCH_SADC]/s");
  eventTree_->Branch("S_Triggered",      b_S_Triggered_,       "S_Triggered[nCH_SADC]/I");
  eventTree_->Branch("S_WaveStartTime",  b_S_WaveStartTime_,   "S_WaveStartTime[nCH_SADC]/D");
  eventTree_->Branch("S_PeakTime",       b_S_PeakTime_,        "S_PeakTime[nCH_SADC]/D");
  eventTree_->Branch("S_ADC",            b_S_ADC_,             "S_ADC[nCH_SADC]/I");
}

EventFiller::~EventFiller()
{
  fout_->cd();
  eventTree_->Write();
  fout_->Write();
  fout_->Close();
  delete fout_;

  delete[] b_F_PmtID_;  delete[] b_F_Triggered_;  delete[] b_F_NDP_;
  delete[] b_F_THR_;    delete[] b_F_WaveStartTime_;  delete[] b_F_Pedestal_;
  delete[] b_F_Waveform_;

  delete[] b_S_PmtID_;  delete[] b_S_Triggered_;  delete[] b_S_ADC_;
  delete[] b_S_THR_;    delete[] b_S_WaveStartTime_;  delete[] b_S_PeakTime_;
}

void EventFiller::Fill(EventInfo* eFADC, EventInfo* eSADC, FChannelData* fCh, AChannelData* aCh)
{
  b_TrgNum_     = eFADC->GetTriggerNumber();
  b_TCBTRGTime_ = (double)eFADC->GetTCBTriggerTime();

  const double trgTimeFADC = (double)eFADC->GetTriggerTime();
  const double trgTimeSADC = (double)eSADC->GetTriggerTime();
  const double tcbTimeSADC = (double)eSADC->GetTCBTriggerTime();

  // FADC channels
  int hasFADCOverThr = 0;
  for ( int iCH=0; iCH<nF_; ++iCH ) {
    FChannel* ch = (FChannel*)fCh->Get(iCH);
    const int ndp = ch->GetSize();
    const unsigned short* wave = ch->GetWaveform();
    const int ped = (int)ch->GetPedestal();
    const int thr = runInfo_.F_THR[iCH];

    b_F_PmtID_[iCH]         = ch->GetID();
    b_F_Triggered_[iCH]     = ch->GetBit();
    b_F_Pedestal_[iCH]      = (short)ped;
    b_F_NDP_[iCH]           = ndp;
    b_F_THR_[iCH]           = (unsigned short)thr;
    b_F_WaveStartTime_[iCH] = trgTimeFADC - runInfo_.F_DLY[iCH];
    b_F_Waveform_[iCH].assign(wave, wave + ndp);

    for ( int i=0; i<ndp; ++i ) {
      if ( (int)wave[i] > ped + thr ) { ++hasFADCOverThr; break; }
    }
  }
  b_EventType_ = (hasFADCOverThr > 0) ? 1 : 0;

  // SADC channels
  bool hasSADCOverThr = false;
  for ( int iCH=0; iCH<nS_; ++iCH ) {
    AChannel* ch = (AChannel*)aCh->Get(iCH);
    const int adc = (int)ch->GetADC();

    b_S_PmtID_[iCH]         = ch->GetID();
    b_S_Triggered_[iCH]     = ch->GetBit();
    b_S_ADC_[iCH]           = adc;
    b_S_THR_[iCH]           = (unsigned short)runInfo_.S_THR[iCH];
    b_S_WaveStartTime_[iCH] = trgTimeSADC - runInfo_.S_DLY[iCH];
    b_S_PeakTime_[iCH]      = (double)ch->GetTime() - (tcbTimeSADC - runInfo_.S_DLY[iCH]);

    if ( adc > runInfo_.S_THR[iCH] ) hasSADCOverThr = true;
  }
  if ( hasSADCOverThr ) b_EventType_ += 2;

  eventTree_->Fill();
}
