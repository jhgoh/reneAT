
#include <iostream>
#include <cstdio>

R__LOAD_LIBRARY(libRawObjs)

using namespace std;

void merge_FADC_SADC(int run, int maxsubrun, int fadcSubrun, int sadcSubrun, int sadcEvent, unsigned int sadcTrgnum, const char* DataDir){

    char run_str[1000000];
    sprintf(run_str, "%06d", run);

    // Save files //
    TFile *outf = nullptr;
    TTree* out_t_tree = nullptr;
    EventInfo* out_eventinfo_fadc = nullptr; EventInfo* out_eventinfo_sadc = nullptr;
    FChannelData* out_fchanneldata = nullptr; AChannelData* out_achanneldata = nullptr;
    bool newOutFlag = true;
    bool SubrunEnd = false;
    bool flag_overMaxSubrun = false;
    ////////////////


    // check tool ////
    int TheNumberOfEvent = 0;
    TH1D* h_missing = new TH1D("h_missing", "", 5, 0, 5);
    int F_prevTrgN = sadcTrgnum; int S_prevTrgN = sadcTrgnum;
    TH2D* h2_trgNumDiffCase = new TH2D("h2_trgNumDiffCase", "h2_trgNumDiffCase", 100, 0, 100, 100, 0, 100);
    //////////////////
    
    int total_events = 0; 
    int final_lost_events_fadc = 0; int final_lost_events_sadc = 0;
    int middle_lost_events_fadc = 0; int middle_lost_events_sadc = 0;

    bool fadcEndSub = true; bool sadcEndSub = true;
    unsigned int fadcTrgnum = 0;

    TFile *inf_fadc = nullptr; TFile *inf_sadc = nullptr;
    TTree* t_tree_fadc = nullptr; TTree* t_tree_sadc = nullptr; 
    EventInfo* eventinfo_fadc = nullptr; EventInfo* eventinfo_sadc = nullptr;
    FChannelData* fchanneldata = nullptr; AChannelData* achanneldata = nullptr;
 
    int ifadc = 0; int isadc = sadcEvent;
    while(1){

        if( fadcSubrun > maxsubrun && sadcSubrun > maxsubrun ) break;

        cout<<"FADC subrun = "<<fadcSubrun<<", SADC subrun = "<<sadcSubrun<<endl;

        // for fadc subrun
        if(fadcEndSub){
            newOutFlag = true;
            
            fadcEndSub = false;

            char fadcsubrun_str[100000];
            sprintf(fadcsubrun_str, "%05d", fadcSubrun);

            inf_fadc = TFile::Open(Form("%s/FADC_%s.root.%s", DataDir, run_str, fadcsubrun_str), "read");
            
            //
            t_tree_fadc = (TTree*)inf_fadc->Get("AbsEvent");
            eventinfo_fadc = new EventInfo();
            fchanneldata = new FChannelData();
            t_tree_fadc->SetBranchAddress("EventInfo", &eventinfo_fadc);
            t_tree_fadc->SetBranchAddress("FChannelData", &fchanneldata);

            TheNumberOfEvent = t_tree_fadc->GetEntries();
        }

        // for sadc subrun
        if(sadcEndSub){
            sadcEndSub = false;

            char sadcsubrun_str[100000];
            sprintf(sadcsubrun_str, "%05d", sadcSubrun);

            inf_sadc = TFile::Open(Form("%s/SADC_%s.root.%s", DataDir, run_str, sadcsubrun_str), "read");

            //
            t_tree_sadc = (TTree*)inf_sadc->Get("AbsEvent");
            eventinfo_sadc = new EventInfo();
            achanneldata = new AChannelData();
            t_tree_sadc->SetBranchAddress("EventInfo", &eventinfo_sadc);
            t_tree_sadc->SetBranchAddress("AChannelData", &achanneldata);

        }
    
        // Save files
        if(newOutFlag){
            newOutFlag = false;

            char out_subrun_str[100000];
            sprintf(out_subrun_str, "%05d", fadcSubrun);

            outf = TFile::Open(Form("%s/Merged/MERGED_%s.root.%s", DataDir, run_str, out_subrun_str), "recreate");

            out_t_tree = new TTree("AbsEvent", "AbsEvent");
            out_eventinfo_fadc = new EventInfo(); out_eventinfo_sadc = new EventInfo();
            out_fchanneldata = new FChannelData(); out_achanneldata = new AChannelData();
          
            out_t_tree->Branch("EventInfo_FADC", &out_eventinfo_fadc); 
            out_t_tree->Branch("EventInfo_SADC", &out_eventinfo_sadc); 
            out_t_tree->Branch("FChannelData_FADC", &out_fchanneldata); 
            out_t_tree->Branch("AChannelData_SADC", &out_achanneldata); 

        }

        // getting each event from data.
        while(1){
            if(fadcSubrun>maxsubrun) { t_tree_fadc->GetEntry(0); final_lost_events_sadc++; flag_overMaxSubrun = true;  }
            else { t_tree_fadc->GetEntry(ifadc); }

            if(sadcSubrun>maxsubrun) { t_tree_sadc->GetEntry(0); final_lost_events_fadc++; flag_overMaxSubrun = true; }
            else { t_tree_sadc->GetEntry(isadc); }

            // main ////
            unsigned int trgNum_fadc = eventinfo_fadc->GetTriggerNumber();
            unsigned int trgNum_sadc = eventinfo_sadc->GetTriggerNumber();


            if( ifadc==0 || (isadc==sadcEvent || isadc==0) ) cout<<"[START] Subrun (FADC, SADC) = ("<<fadcSubrun<<", "<<sadcSubrun<<"), Before trgNum = "<<sadcTrgnum<<", FADC trg # = "<<trgNum_fadc<<", SADC trg # = "<<trgNum_sadc<<endl;
            

            // Save files
            if(fadcSubrun<=maxsubrun && trgNum_fadc == trgNum_sadc) { 

                *out_eventinfo_fadc = *eventinfo_fadc;
                *out_eventinfo_sadc = *eventinfo_sadc;
            
                out_fchanneldata = (FChannelData*)fchanneldata->Clone();
                out_achanneldata = (AChannelData*)achanneldata->Clone();

                out_t_tree->Fill(); 

                total_events++;

            }



            // Counting missing events
            int iFScheck = 0; bool flag_FScheck = true; bool flag_diff = false; 
            bool flag_Fcorrect = false; bool flag_Scorrect = false;

            F_prevTrgN = (double)trgNum_fadc - F_prevTrgN < 0 ? 0 : F_prevTrgN;
            S_prevTrgN = (double)trgNum_sadc - S_prevTrgN < 0 ? 0 : S_prevTrgN;

            int F_trg_diff_num = trgNum_fadc - F_prevTrgN; // 1 is the normal event diff number.
            int S_trg_diff_num = trgNum_sadc - S_prevTrgN; // 1 is the normal event diff number.
            int FS_trg_diff_num = F_trg_diff_num > S_trg_diff_num ? F_trg_diff_num:S_trg_diff_num;

            int countF = 1; int countS = 1; // just flag for the normal event diff number.
            if( !flag_overMaxSubrun ){

                int simul_miss_ref = (trgNum_fadc == trgNum_sadc)? FS_trg_diff_num-1 : 1;
                for(int simultaneous_missing_check=0; simultaneous_missing_check<simul_miss_ref; simultaneous_missing_check++){

                    if( countF < F_trg_diff_num ){ // FADC check
                        if( flag_FScheck ){ 
                            flag_FScheck = false; 
                            cout<<endl;
                            cout<<"[Missing] Subrun (FADC, SADC) = ("<<fadcSubrun<<", "<<sadcSubrun<<")"<<endl; 
                        }
                        iFScheck = 1;
                        cout<<"FADC: Prev TRG num = "<<F_prevTrgN<<", Current TRG num = "<<trgNum_fadc<<endl;
                        flag_diff = true;
                    }

                    if( countS < S_trg_diff_num ){ // SADC check
                        if( flag_FScheck ){ 
                            flag_FScheck = false; 
                            cout<<endl;
                            cout<<"[Missing] Subrun (FADC, SADC) = ("<<fadcSubrun<<", "<<sadcSubrun<<")"<<endl; 
                        }
                        iFScheck += 2;
                        cout<<"SADC: Prev TRG num = "<<S_prevTrgN<<", Current TRG num = "<<trgNum_sadc<<endl;
                        flag_diff = true;
                    }

                    if( flag_diff ){
                        h_missing->Fill(iFScheck); h2_trgNumDiffCase->Fill(fadcSubrun, sadcSubrun); 
                        flag_diff = false; iFScheck = 0;
                    }

                }

                // Correcting ~
                if( (!(fadcSubrun > maxsubrun || sadcSubrun > maxsubrun) && (trgNum_fadc != trgNum_sadc))
                    && ( countS < S_trg_diff_num || countF < F_trg_diff_num ) ){

                    if( trgNum_fadc > trgNum_sadc ){ 
                        cout<<"[CORRECTING] * FADC "<<trgNum_sadc<<"th triggered event is missing"<<endl;
                        middle_lost_events_fadc++; 
                        isadc++;
                        flag_Fcorrect = true;
                        F_prevTrgN += 1;
                    }  
                    else{
                        cout<<"[CORRECTING] * SADC "<<trgNum_fadc<<"th triggered event is missing"<<endl; 
                        middle_lost_events_sadc++;
                        ifadc++;
                        flag_Scorrect = true;
                        S_prevTrgN += 1;
                    }

                }

            }

            fadcTrgnum = trgNum_fadc;
            //sadcTrgnum = trgNum_sadc; fadcTrgnum = trgNum_fadc; // for the next subrun

            if( !flag_Fcorrect && !flag_Scorrect ){ 
                ifadc++; isadc++; 
                F_prevTrgN = trgNum_fadc; S_prevTrgN = trgNum_sadc;
            }
            else if( flag_Fcorrect && !flag_Scorrect ) { S_prevTrgN = trgNum_sadc; }
            else if( !flag_Fcorrect && flag_Scorrect ) { F_prevTrgN = trgNum_fadc; }

            ///////////


            if( ifadc>=t_tree_fadc->GetEntries() ) { cout<<"[END] fadc trg #= "<<trgNum_fadc<<endl; ifadc = 0; fadcEndSub = true; break; }
            if( isadc>=t_tree_sadc->GetEntries() ) { cout<<"[END] sadc trg #= "<<trgNum_sadc<<endl; isadc = 0; sadcEndSub = true; break; }
        }

        if(fadcEndSub){ 

            // Save files
            if(!newOutFlag && fadcSubrun<=maxsubrun){
                outf->cd();
                out_t_tree->Write();
                outf->Close();
                delete outf;
                delete out_eventinfo_fadc; delete out_fchanneldata;
                delete out_eventinfo_sadc; delete out_achanneldata;

                SubrunEnd = true;
            }

            fadcSubrun++; 
            if(fadcSubrun<=maxsubrun) { inf_fadc->Close(); delete inf_fadc; delete eventinfo_fadc; delete fchanneldata; }
            else { fadcEndSub = false; }
        }

        if(sadcEndSub){ 
            sadcSubrun++;
            if(sadcSubrun<=maxsubrun) { inf_sadc->Close(); delete inf_sadc; delete eventinfo_sadc; delete achanneldata; }
            else { sadcEndSub = false; }
        }

        if(SubrunEnd){

            // THIS PART IS NECESSARY.
            // "isadc" indicates the next SADC subrun's entry to be processed.
            cout<<endl; cout<<"********************************************"<<endl;
            cout<<"Below log will be used for the next subrun!"<<endl;
            cout<<"  Trigger number range: [0 ~ 4,294,967,295]"<<endl;
            cout<<"********************************************"<<endl;
            cout<<"final FADC = "<<fadcSubrun<<endl; cout<<"final FADC_evt = "<<ifadc<<endl; cout<<"final before_FADC_trgnum = "<<F_prevTrgN<<endl;//fadcTrgnum<<endl;
            cout<<"final SADC = "<<sadcSubrun<<endl; cout<<"final SADC_evt = "<<isadc<<endl; cout<<"final before_SADC_trgnum = "<<S_prevTrgN<<endl;//sadcTrgnum<<endl;
            cout<<"********************************************"<<endl; cout<<endl;

            break;

        }
    }

    cout<<"********************************************"<<endl;
    cout<<"Merged Info. of run #"<<run<<" - subrun #"<<fadcSubrun-1<<endl;
    cout<<"********************************************"<<endl;
    cout<<"Total merged events = "<<total_events<<endl;
    cout<<"--------------------------------------------"<<endl;
    cout<<"* Missing Events *"<<endl;
    int tot_missing = (double)fadcTrgnum - sadcTrgnum - total_events;
    cout<<"Total missing = "<<endl;
    cout<<" (1) Trg number - Save number = "<<tot_missing<<endl;
    cout<<" (2) Check (except 'By Run-End') = "<<h_missing->GetBinContent(4)+h_missing->GetBinContent(2)+h_missing->GetBinContent(3)<<endl;
    cout<<"FADC / SADC missing events at the same time = "
        /*<<tot_missing-middle_lost_events_fadc-middle_lost_events_sadc<<" "*/<<h_missing->GetBinContent(4)<<endl;
    cout<<"only FADC missing events = "/*<<middle_lost_events_fadc<<" "*/<<h_missing->GetBinContent(2)<<endl;
    cout<<"only SADC missing events = "/*<<middle_lost_events_sadc<<" "*/<<h_missing->GetBinContent(3)<<endl;
    cout<<"* By Run-End *"<<endl;
    cout<<"FADC missing events = "<<final_lost_events_sadc<<endl;
    cout<<"SADC missing events = "<<final_lost_events_fadc<<endl;
    cout<<"********************************************"<<endl; cout<<endl;

    gStyle->SetPalette(1);
    TCanvas* c_check = new TCanvas("c_check", "", 2600, 2400);
    //c_check->Divide(3, 1);
    //c_check->cd(1); h_trgNumDiffCase->Draw("hist");
    //c_check->cd(2); g_trgNumDiff->Draw("ap");
    //c_check->cd(3); h2_trgNumDiffCase->Draw("colz");
    c_check->SetLogz(); c_check->SetGridx(); c_check->SetGridy(); 
    c_check->SetLeftMargin(0.13); c_check->SetRightMargin(0.15);
    h2_trgNumDiffCase->Draw("colz");
    h2_trgNumDiffCase->GetXaxis()->SetTitle("FADC Subrun");
    h2_trgNumDiffCase->GetYaxis()->SetTitle("SADC Subrun");
    TGraph* g_refline = new TGraph(); g_refline->SetPoint(0, 0, 0); g_refline->SetPoint(1, 100, 100); g_refline->Draw("l same");
    TLine* l_xline = new TLine(); TLine* l_yline = new TLine();
    l_xline->DrawLine(fadcSubrun-1+0.5,0,fadcSubrun-1+0.5,100); l_yline->DrawLine(0,sadcSubrun-1+0.5,100,sadcSubrun-1+0.5);
    l_xline->SetLineColor(kBlue); l_yline->SetLineColor(kBlue);
    c_check->SaveAs(Form("%s/PNG/merge_FADC_SADC_run%d_subrun%d.png", DataDir, run, fadcSubrun-1));


    return;
}
