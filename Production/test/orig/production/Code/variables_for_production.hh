#ifndef VARIABLES_HH
#define VARIABLES_HH 

#include <vector>

// Constants
const int nFADC = 1;
const int nSADC = 1;
const int nchFADC = /*2 * nFADC;*/ 4 * nFADC;//2;
const int nchSADC = 30 * nSADC; //32 * nSADC;

// TCB trigger time const
const unsigned long TimeConst_fine = (0b01111100 * 8.);
const unsigned long TimeConst_coarse = (0xFFFFFF * 1000.);
const unsigned long TimeConst = TimeConst_fine + TimeConst_coarse;

const unsigned int TrgNumConst = (0xFFFFFFFF * 1);

double prev_tcbtrgTime = 0;
double tcbtrgCycle = 0;

// Flags
bool FevtTypeFlag;
bool SevtTypeFlag;

int eventType; // 1: FADC, 2: SADC, 3: FADC + SADC
unsigned int trgNumber;
double tcbtrgTime;

// Variables 
// FADC
unsigned long Fdelay[nchFADC];
unsigned short Fthr[nchFADC];
int Fpid[nchFADC];
int Fbit[nchFADC];
//unsigned long FstartTime[nchFADC];
double FstartTime[nchFADC];
int Fndp[nchFADC];
std::vector<unsigned short> Fwaveform[nchFADC]; 
std::vector<std::vector<unsigned short>*> FFwaveform(nchFADC);
unsigned short Fpedestal[nchFADC];

// SADC
unsigned long Sdelay[nchSADC];
unsigned short Sthr[nchSADC];
int Spid[nchSADC];
int Sbit[nchSADC];
//unsigned long SstartTime[nchSADC];
double SstartTime[nchSADC];
//unsigned long SpeakTime[nchSADC];
double SpeakTime[nchSADC];
unsigned int Sadc[nchSADC];


typedef struct RegisteredValue{
    std::vector<int> fadcPID;
    std::vector<int> fadcDLY;
    std::vector<int> fadcTHR;

    std::vector<int> sadcPID;
    std::vector<int> sadcDLY;
    std::vector<int> sadcTHR;
} RV;



// Function
void initializing(){

    FevtTypeFlag = false;
    SevtTypeFlag = false;

    eventType = 0;
    trgNumber = -99;
    tcbtrgTime = -99;

    // FADC
    for(int ich=0; ich<nchFADC; ich++){
        Fpid[ich] = -99;
        Fbit[ich] = -99;
        FstartTime[ich] = -99;
        Fndp[ich] = -99;
        Fpedestal[ich] = -99;
        Fwaveform[ich].clear();
    }
    FFwaveform.clear();

    // SADC
    for(int ich=0; ich<nchSADC; ich++){
        Spid[ich] = -99;
        Sbit[ich] = -99;
        SpeakTime[ich] = -99;
        Sadc[ich] = -99;
    }
    
}

void reading_DLY_THR(char* run_str, const char* DataDir){

    RV run;

    bool flag_fadc;
    bool flag_sadc;

    bool flag_nadc;
    bool flag_pid;
    bool flag_dly;
    bool flag_thr;


    int nadc = 0;
    int channel = 0;

    int val = 0;

    ifstream inf_txt;
    inf_txt.open(Form("%s/PRD/Run%s_DLY_THR.log", DataDir, run_str));

    string line;

  while ( inf_txt.good() ) {
    getline(inf_txt, line);

    if ( line.empty() ) continue;

    istringstream iss(line);

    string key;


    iss >> key;
    if (iss.fail() || key.length() == 0 ) { continue; }
   
    if ( !strcmp(key.data(), "WJ") ){ 
        flag_fadc = false;
        flag_sadc = false;

        flag_nadc = false;
        flag_pid = false;
        flag_dly = false;
        flag_thr = false;

    }

    iss >> key;
    if ( !strcmp(key.data(), "FADC") ) { flag_fadc = true; }
    else { flag_sadc = true; }

    iss >> key;
    if ( !strcmp(key.data(), "NADC") ) { flag_nadc = true; }
    else if ( !strcmp(key.data(), "PID") ) { flag_pid = true; }
    else if ( !strcmp(key.data(), "DLY") ) { flag_dly = true; }
    else if ( !strcmp(key.data(), "THR") ) { flag_thr = true; }

    //cout<<key<<endl;

    iss >> key;
    if ( !strcmp(key.data(), "(registered)") ) { iss >> key; }


    // module
    if ( flag_nadc ) { iss >> nadc; }
    
    if ( flag_fadc ) { channel = nchFADC; }
    else if ( flag_sadc ) { channel = nchSADC; }


    // pid 
    if ( flag_pid ) {
        for(int inum = 0; inum < channel; inum++){ 
            if ( flag_fadc ) { iss >> val; run.fadcPID.push_back(val); }
            else if ( flag_sadc ) { iss >> val; run.sadcPID.push_back(val); }

            //if ( flag_fadc ) { cout<<inum<<" "<<run.fadcPID[inum]<<endl; }
            //else if ( flag_sadc ) { cout<<inum<<" "<<run.sadcPID[inum]<<endl; }

        }
    }

    // dly 
    if ( flag_dly ) {
        for(int inum = 0; inum < channel; inum++){
            if ( flag_fadc ) { iss >> val; run.fadcDLY.push_back(val); }
            else if ( flag_sadc ) { iss >> val; run.sadcDLY.push_back(val); }
            
            //if ( flag_fadc ) { cout<<inum<<" "<<run.fadcDLY[inum]<<endl; }
            //else if ( flag_sadc ) { cout<<inum<<" "<<run.sadcDLY[inum]<<endl; }

        }
    }


    // thr 
    if ( flag_thr ) {
        for(int inum = 0; inum < channel; inum++){
            if ( flag_fadc ) { iss >> val; run.fadcTHR.push_back(val); }
            else if ( flag_sadc ) { iss >> val; run.sadcTHR.push_back(val); }

            //if ( flag_fadc ) { cout<<inum<<" "<<run.fadcTHR[inum]<<endl; }
            //else if ( flag_sadc ) { cout<<inum<<" "<<run.sadcTHR[inum]<<endl; }

        }
    }


  }


  inf_txt.close();



  // assigning ~
  for(int ich=0; ich<nchFADC; ich++){ 
      Fdelay[ich] = (unsigned long)run.fadcDLY.at(ich); 
      Fthr[ich] = (unsigned long)run.fadcTHR.at(ich); 
  }
  for(int ich=0; ich<nchSADC; ich++){ 
      Sdelay[ich] = (unsigned long)run.sadcDLY.at(ich); 
      Sthr[ich] = (unsigned long)run.sadcTHR.at(ich); 
  }



  return;

}


void timecorrection(){
    // Time correction
    tcbtrgTime = tcbtrgTime + TimeConst * tcbtrgCycle;
    for( int ich = 0; ich < nchFADC; ich++ ) { FstartTime[ich] = FstartTime[ich] + TimeConst * tcbtrgCycle; }
    for( int ich = 0; ich < nchSADC; ich++ ) { SstartTime[ich] = SstartTime[ich] + TimeConst * tcbtrgCycle; }

    if( tcbtrgTime < prev_tcbtrgTime ){
        tcbtrgTime = tcbtrgTime + TimeConst;
        tcbtrgCycle++;
    }
    prev_tcbtrgTime = tcbtrgTime;
    //cout << tcbtrgTime << endl;

    return;
}

/*void reading_DLY_THR(char* run_str){
    for(int ich=0; ich<nchFADC; ich++) { Fdelay[ich] = -99; Fthr[ich] = -99; }
    for(int ich=0; ich<nchSADC; ich++) { Sdelay[ich] = -99; Sthr[ich] = -99; }

    char str1[100], str2[100], str3[100], str4[100], str5[100];
    FILE* log = fopen(Form("/Data/RAW/%s/PRD/Run%s_DLY_THR.log", run_str, run_str), "r");
    fscanf(log, "%s %s %s %s %s %lu %lu %lu %lu",  // DLY of FADC
           str1, str2, str3, str4, str5,
           &Fdelay[0], &Fdelay[1], &Fdelay[2], &Fdelay[3]);
    fscanf(log, "%s %s %s %s %s %hu %hu %hu %hu", // THR of FADC
           str1, str2, str3, str4, str5,
           &Fthr[0], &Fthr[1], &Fthr[2], &Fthr[3]);
    fscanf(log, "%s %s %s %s %s %lu %lu %lu %lu %lu %lu %lu %lu"
                                "%lu %lu %lu %lu %lu %lu %lu %lu"
                                "%lu %lu %lu %lu %lu %lu %lu %lu"
                                "%lu %lu %lu %lu %lu %lu %lu %lu",  // DLY of SADC
           str1, str2, str3, str4, str5,
           &Sdelay[0], &Sdelay[1], &Sdelay[2], &Sdelay[3], 
           &Sdelay[4], &Sdelay[5], &Sdelay[6], &Sdelay[7], 
           &Sdelay[8], &Sdelay[9], &Sdelay[10], &Sdelay[11],
           &Sdelay[12], &Sdelay[13], &Sdelay[14], &Sdelay[15],
           &Sdelay[16], &Sdelay[17], &Sdelay[18], &Sdelay[19],
           &Sdelay[20], &Sdelay[21], &Sdelay[22], &Sdelay[23], 
           &Sdelay[24], &Sdelay[25], &Sdelay[26], &Sdelay[27],
           &Sdelay[28], &Sdelay[29], &Sdelay[30], &Sdelay[31]);
    fscanf(log, "%s %s %s %s %s %hu %hu %hu %hu %hu %hu %hu %hu"
                                "%hu %hu %hu %hu %hu %hu %hu %hu"
                                "%hu %hu %hu %hu %hu %hu %hu %hu"
                                "%hu %hu %hu %hu %hu %hu %hu %hu",  // THR of SADC
           str1, str2, str3, str4, str5,
           &Sthr[0], &Sthr[1], &Sthr[2], &Sthr[3], 
           &Sthr[4], &Sthr[5], &Sthr[6], &Sthr[7], 
           &Sthr[8], &Sthr[9], &Sthr[10], &Sthr[11],
           &Sthr[12], &Sthr[13], &Sthr[14], &Sthr[15],
           &Sthr[16], &Sthr[17], &Sthr[18], &Sthr[19],
           &Sthr[20], &Sthr[21], &Sthr[22], &Sthr[23], 
           &Sthr[24], &Sthr[25], &Sthr[26], &Sthr[27],
           &Sthr[28], &Sthr[29], &Sthr[30], &Sthr[31]);
    fclose(log);
}*/


#endif
