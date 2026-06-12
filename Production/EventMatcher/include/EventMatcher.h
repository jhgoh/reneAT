#ifndef EventMatcher_H
#define EventMatcher_H

#include "EventFiller.h"
#include "RawObjs/EventInfo.hh"
#include "RawObjs/AChannelData.hh"

#include "TFile.h"
#include "TTree.h"

#include <string>
#include <vector>

class EventMatcher {
public:
  // fNamesSADC: all SADC subrun filenames for the run (in order).
  // SADC state (subrun index, entry index) persists across Process() calls
  // so that consecutive FADC subruns continue scanning from where they left off.
  EventMatcher(const std::vector<std::string>& fNamesSADC, bool verbose = true);
  ~EventMatcher();

  // Process one FADC subrun. Returns number of matched events.
  int Process(const std::string& fNameOut,
              const std::string& subrun,
              const std::string& fNameFADC,
              const EventFiller::RunInfo& runInfo);

private:
  bool verbose_;
  std::vector<std::string> fNamesSADC_;

  // Persistent SADC state across Process() calls
  int iSubrunSADC_;
  int iEntrySADC_;
  int nEntrySADC_;
  TFile* fSADC_;
  TTree* tSADC_;
  EventInfo* eSADC_;
  AChannelData* aChannel_;

  bool openSADC(int idx);
};

#endif
