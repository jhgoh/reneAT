#include "EventMatcher.h"
#include "RawObjs/FChannelData.hh"

#include <iostream>
using namespace std;

EventMatcher::EventMatcher(const std::vector<std::string>& fNamesSADC, bool verbose)
  : verbose_(verbose), fNamesSADC_(fNamesSADC),
    iSubrunSADC_(0), iEntrySADC_(0), nEntrySADC_(0),
    fSADC_(nullptr), tSADC_(nullptr), eSADC_(nullptr), aChannel_(nullptr)
{
  if ( !fNamesSADC_.empty() ) openSADC(0);
}

EventMatcher::~EventMatcher()
{
  if ( fSADC_ ) fSADC_->Close();
}

bool EventMatcher::openSADC(int idx)
{
  if ( idx >= (int)fNamesSADC_.size() ) return false;
  if ( fSADC_ ) fSADC_->Close();
  iSubrunSADC_ = idx;
  iEntrySADC_  = 0;
  fSADC_ = TFile::Open(fNamesSADC_[idx].c_str());
  tSADC_ = (TTree*)fSADC_->Get("AbsEvent");
  tSADC_->SetBranchAddress("EventInfo",    &eSADC_);
  tSADC_->SetBranchAddress("AChannelData", &aChannel_);
  nEntrySADC_ = tSADC_->GetEntries();
  return true;
}

int EventMatcher::Process(const std::string& fNameOut,
                          const std::string& subrun,
                          const std::string& fNameFADC,
                          const EventFiller::RunInfo& runInfo)
{
  EventFiller filler(fNameOut, runInfo);

  TFile* fFADC = TFile::Open(fNameFADC.c_str());
  TTree* tFADC = (TTree*)fFADC->Get("AbsEvent");

  EventInfo* eFADC = nullptr;
  FChannelData* fChannel = nullptr;
  tFADC->SetBranchAddress("EventInfo",    &eFADC);
  tFADC->SetBranchAddress("FChannelData", &fChannel);

  int nEvent = 0;
  const int nEntryFADC = tFADC->GetEntries();
  for ( int iEntryFADC=0; iEntryFADC<nEntryFADC; ++iEntryFADC ) {
    tFADC->GetEntry(iEntryFADC);
    const int trgNumFADC = eFADC->GetTriggerNumber();

    if ( verbose_ ) {
      cout << "Processing subrun=" << subrun
           << " Entry=" << (iEntryFADC+1) << '/' << nEntryFADC
           << " Event=" << trgNumFADC << '\r' << flush;
    }

    bool isMatched = false, isToSkip = false;
    while ( true ) {
      if ( iEntrySADC_ >= nEntrySADC_ ) {
        if ( !openSADC(iSubrunSADC_ + 1) ) break;
      }

      tSADC_->GetEntry(iEntrySADC_);
      const int trgNumSADC = eSADC_->GetTriggerNumber();

      if ( trgNumSADC > trgNumFADC ) {
        isToSkip = true;
        break;
      }

      ++iEntrySADC_;
      if ( trgNumSADC == trgNumFADC ) {
        isMatched = true;
        break;
      }
    }
    if ( isToSkip ) continue;

    if ( isMatched ) {
      ++nEvent;
      filler.Fill(eFADC, eSADC_, fChannel, aChannel_);
    }
  }
  if ( verbose_ ) {
    cout << "\nMatched events=" << nEvent << endl;
  }

  fFADC->Close();
  return nEvent;
}
