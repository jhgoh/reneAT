
R__LOAD_LIBRARY(libRawObjs)

#include "variables_for_production.hh"

void production_from_merged_v3(int run, int subrun, const char* DataDir){
    
    char run_str[1000000];
    sprintf(run_str, "%06d", run);
    char subrun_str[1000000];
    sprintf(subrun_str, "%05d", subrun);


    //+++++++
    // Input
    //+++++++
    TFile* inf = new TFile(Form("%s/Merged/MERGED_%s.root.%s", DataDir, run_str, subrun_str), "read");

    TTree* in_t_tree = (TTree*)inf->Get("AbsEvent");
    EventInfo* in_eventinfo_fadc = new EventInfo(); 
    EventInfo* in_eventinfo_sadc = new EventInfo();
    FChannelData* in_fchanneldata = new FChannelData(); 
    AChannelData* in_achanneldata = new AChannelData();

    // FADC
    in_t_tree->SetBranchAddress("EventInfo_FADC", &in_eventinfo_fadc);
    in_t_tree->SetBranchAddress("FChannelData_FADC", &in_fchanneldata);
    // SADC
    in_t_tree->SetBranchAddress("EventInfo_SADC", &in_eventinfo_sadc);
    in_t_tree->SetBranchAddress("AChannelData_SADC", &in_achanneldata);

    reading_DLY_THR(run_str, DataDir);


    //++++++++
    // Output
    //++++++++
    TFile* outf = new TFile(Form("%s/PRD/PRD_%s.%s.root", DataDir, run_str, subrun_str), "recreate");
    TTree* out_t_tree = new TTree("Event", "Event");
    out_t_tree->Branch("TrgNum", &trgNumber);
    out_t_tree->Branch("EventType", &eventType);
    out_t_tree->Branch("TCBTRGTime", &tcbtrgTime);

    // FADC
    int nchFADCi = (int)nchFADC;
    out_t_tree->Branch("nCH_FADC", &nchFADCi);
    out_t_tree->Branch("F_PmtID", &Fpid, "F_pmtID[nCH_FADC]/I");
    out_t_tree->Branch("F_THR", &Fthr, "F_THR[nCH_FADC]/s"); // unsigned short
    out_t_tree->Branch("F_Triggered", &Fbit, "F_Triggered[nCH_FADC]/I");
    out_t_tree->Branch("F_WaveStartTime", &FstartTime, "F_WaveStartTime[nCH_FADC]/D");
    out_t_tree->Branch("F_Pedestal", &Fpedestal, "F_Pedestal[nCH_FADC]/s");
    out_t_tree->Branch("F_NDP", &Fndp, "F_NDP[nCH_FADC]/I");
    for(int ich=0; ich<nchFADC; ich++) out_t_tree->Branch(Form("F_Waveform_%d", ich), &Fwaveform[ich]);

    // SADC
    int nchSADCi = (int)nchSADC;
    out_t_tree->Branch("nCH_SADC", &nchSADCi);
    out_t_tree->Branch("S_PmtID", &Spid, "S_PmtID[nCH_SADC]/I");
    out_t_tree->Branch("S_THR", &Sthr, "S_THR[nCH_SADC]/s"); // unsigned short
    out_t_tree->Branch("S_Triggered", &Sbit, "S_Triggered[nCH_SADC]/I");
    out_t_tree->Branch("S_WaveStartTime", &SstartTime, "S_WaveStartTime[nCH_SADC]/D");
    out_t_tree->Branch("S_PeakTime", &SpeakTime, "S_PeakTime[nCH_SADC]/D");
    out_t_tree->Branch("S_ADC", &Sadc, "S_ADC[nCH_SADC]/I");



    //+++++++++++
    // Main part
    //+++++++++++
    cout << in_t_tree->GetEntries() << endl;
    for(int iEntry=0; iEntry<in_t_tree->GetEntries(); iEntry++){
        initializing();
       
        if( in_t_tree->GetEntries() < 10 ) 
            cout<<iEntry<<" / "<<in_t_tree->GetEntries()<<" Producing ... "<<endl;
	else if( iEntry % (in_t_tree->GetEntries()/10) == 0 ) 
            cout<<iEntry<<" / "<<in_t_tree->GetEntries()<<" Producing ... "<<endl;


        in_t_tree->GetEntry(iEntry);
        
        if( (unsigned long) (in_eventinfo_fadc->GetTCBTriggerTime() - in_eventinfo_sadc->GetTCBTriggerTime()) != 0 ) 
            { cout<<"Something wrong in "<<iEntry<<" event in TCBTRGTIME !"<<endl; continue; }

        if( in_eventinfo_fadc->GetTriggerNumber() - in_eventinfo_sadc->GetTriggerNumber() != 0 )
            { cout<<"Something wrong in "<<iEntry<<" event in TRGNUM !"<<endl; continue; }

        tcbtrgTime = in_eventinfo_fadc->GetTCBTriggerTime();
        trgNumber = in_eventinfo_fadc->GetTriggerNumber();

        // FADC
        for(int ich=0; ich<nchFADC; ich++){
            
            FChannel* fchannel = (FChannel*)in_fchanneldata->Get(ich);
            
            // | - from DAQ start  - > [ window ]
	    // ^ --------------------- ^: FstartTime
            FstartTime[ich] = (double)in_eventinfo_fadc->GetTriggerTime() - Fdelay[ich];

            //FstartTime[ich] = (double)in_eventinfo_fadc->GetTCBTriggerTime() - Fdelay[ich];
            //cout<<FstartTime[ich]<<" "<<in_eventinfo_fadc->GetTCBTriggerTime()<<" "<<Fdelay[ich]<<endl;
            
            Fpid[ich] = fchannel->GetID();
            Fbit[ich] = fchannel->GetBit();
            Fwaveform[ich] = std::vector<unsigned short>(fchannel->GetWaveform(), 
                                                         fchannel->GetWaveform() + fchannel->GetSize());
            Fndp[ich] = fchannel->GetSize();
            Fpedestal[ich] = fchannel->GetPedestal();

            if( !FevtTypeFlag ){
                for(int ipnt=0; ipnt<Fndp[ich]; ipnt++){
                    if( Fwaveform[ich][ipnt] - Fpedestal[ich] > Fthr[ich] ) 
                        //{ eventType = 1; FevtTypeFlag = true; break; }
                        { if(Fbit[ich]==0){
                            cout<<" The case that fadc is not triggered when it should be triggered"<<endl;
                            cout<<"iEntry = "<<iEntry<<", ich = "<<ich<<" - "<<ipnt<<" "<<Fbit[ich]<<" "<<Fwaveform[ich][ipnt]<<" - "<<Fpedestal[ich]<<" "<<Fwaveform[ich][ipnt] - Fpedestal[ich]<<" "<<Fthr[ich]<<""<<endl;} eventType = 1; FevtTypeFlag = true; /*break;*/ } // to check
                }
            }
            
/*            cout<<ich<<" "<<Fwaveform[ich][120]<<endl;
            cout<<endl;*/

        }

        // SADC
        for(int ich=0; ich<nchSADC; ich++){

            AChannel* achannel = (AChannel*)in_achanneldata->Get(ich);
           
            SstartTime[ich] = (double)in_eventinfo_sadc->GetTCBTriggerTime() - Sdelay[ich]; 
            SpeakTime[ich] = (double)achannel->GetTime() - SstartTime[ich];
            /*SpeakTime[ich] // It can't be negative!
                = (double)achannel->GetTime() - SstartTime[ich] < 0 ?
                  -99 : (double)achannel->GetTime() - SstartTime[ich];*/

            // | - from DAQ start  - > [ window ]
	    // ^ --------------------- ^: SstartTime
            SstartTime[ich] = (double)in_eventinfo_sadc->GetTriggerTime() - Sdelay[ich]; 

            //cout<<SpeakTime[ich]<<" "<<in_eventinfo_sadc->GetTCBTriggerTime()<<" "<<Sdelay[ich]<<" "<<achannel->GetTime()<<endl;
            
            Spid[ich] = achannel->GetID();
            Sbit[ich] = achannel->GetBit();
            Sadc[ich] = achannel->GetADC();
            
            if( Sadc[ich] > Sthr[ich] && !SevtTypeFlag) 
                { eventType = eventType + 2*1; SevtTypeFlag = true; continue; }

        }


        out_t_tree->Fill();
    }


    //++++++
    // Save
    //++++++
    outf->cd();
    out_t_tree->Write();
    outf->Close();

    return;
}

