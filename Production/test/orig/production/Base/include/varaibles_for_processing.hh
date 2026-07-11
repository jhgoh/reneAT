#ifndef variables_for_processing_HH
#define variables_for_processing_HH 

#include <vector>

/////////////////////////////////////////////////////
// Search " Hardcode " to modify several varibles. //
/////////////////////////////////////////////////////


// For input file //
// It's the same with production header //

// Constants
const double sampRateFADC = 2.; // [ns / 1 sample]
const double sampRateSADC = 16.; // [ns / 1 sample]

const int nFADC = 1; // Hardcode
const int nSADC = 1; // Hardcode
const int nchFADC = 4 * nFADC;
const int nchSADC = 32 * nSADC;

// TCB trigger time const
const unsigned long TimeConst_fine = (0b01111100 * 8.);
const unsigned long TimeConst_coarse = (0xFFFFFF * 1000.);
const unsigned long TimeConst = TimeConst_fine + TimeConst_coarse;

int subInterval = 20; // [minute] // Hardcode

const unsigned int TrgNumConst = (0xFFFFFFFF * 1);


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



// Functions

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

////////////////////////////////////////////////////



// For NTP file //

// Consts.
const double Q_elec = 1.6 * 1e-19; // [C]
const double Fgain = 1e7;
const double Sgain = 1e7;
const double convertFADCtoQ = (2.5 / pow(2, 12)) * (sampRateFADC * 1e-9) * 1e12 / 50. / (Q_elec * Fgain * 1e12); 
// adc -> npe
const double convertSADCtoQ = (2. / pow(2, 12)) * (sampRateSADC * 1e-9) * 1e12 / 50.;// / (Q_elec * Sgain * 1e12); 
// adc -> pC
// (detailed explanation for conversion) //
// [V] / [adc]  * [s] * [pico conversion] / [ohm] / [electron charge * gain] * [pico conversion]
// = [pC] / [Q of electron in pC]
// *Basic: [C] = [A] * [s], [A] = [V] / [ohm]


double prev_FstartTime[nchFADC] = { 0, };
int F_numCycle[nchFADC] = { 0, };
double prev_SstartTime[nchSADC] = { 0, };
int S_numCycle[nchSADC] = { 0, };



// - Hardcode - //

// Noise filtering
const int noiseRef = 10; // adc value

// For pedestal calculation.
const int pedRange1 = 0; 
const int pedRange2 = 100;

// For Q summation.
const int sigRange1 = 100;
const int sigRange2 = 400;
//const int prevBin = 7; 
//const int binInterval = 50;

// PSD
const int QtailStartOffset = 15;
int QtailRange1 = 0; // not hardcoded, just initialization: sorry ~
int QtailRange2 = 0; // not hardcoded, just initialization: sorry ~

// Veto pannel
int VetoPanel[nchSADC] = {
    1, 1,
    2, 2,
    3, 3,
    4, 4,
    5, 5,
    6, 6,
    7, 7,
    8, 8,
    9, 9,
    10, 10,
    11, 11,
    12, 12,
    13, 13,
    14, 14,
    15, 15,
    16, // deadzone 
    17 // deadzone
};
// - Hardcode done - //


// - For saving data - //
unsigned int NTPtrgNumber;
int NTPeventType;

// FADC
double NTPinnerNPE;
double NTPinnerRtail; // Qtail / Qtotal
double NTPinnerEventTime;

// SADC
std::vector<double> NTPvetopC;
std::vector<int> NTPvetoPanel;
std::vector<double> NTPvetoEventTime;




////////////////////////////////////////////////////
// functions
void setbranch(TTree* t){

    t->SetBranchAddress("TrgNum", &trgNumber);
    t->SetBranchAddress("EventType", &eventType);
    t->SetBranchAddress("TCBTRGTime", &tcbtrgTime);

    // FADC
    int nchFADCi = -99;
    t->SetBranchAddress("nCH_FADC", &nchFADCi);
    t->SetBranchAddress("F_PmtID", &Fpid);
    t->SetBranchAddress("F_THR", &Fthr); // unsigned short
    t->SetBranchAddress("F_Triggered", &Fbit);
    t->SetBranchAddress("F_WaveStartTime", &FstartTime);
    t->SetBranchAddress("F_Pedestal", &Fpedestal);
    t->SetBranchAddress("F_NDP", &Fndp);
    for(int ich=0; ich<nchFADC; ich++){
        FFwaveform[ich] = new std::vector<unsigned short>;
        t->SetBranchAddress(Form("F_Waveform_%d", ich), &FFwaveform[ich]);
    }

    // SADC
    int nchSADCi = -99;
    t->SetBranchAddress("nCH_SADC", &nchSADCi);
    t->SetBranchAddress("S_PmtID", &Spid);
    t->SetBranchAddress("S_THR", &Sthr); // unsigned short
    t->SetBranchAddress("S_Triggered", &Sbit);
    t->SetBranchAddress("S_WaveStartTime", &SstartTime);
    t->SetBranchAddress("S_PeakTime", &SpeakTime);
    t->SetBranchAddress("S_ADC", &Sadc);

    return;

}

void branch(TTree* t){

    t->Branch("TrgNumber", &NTPtrgNumber);
    t->Branch("EventType", &NTPeventType);

    t->Branch("InnerNPE", &NTPinnerNPE);
    t->Branch("InnerRtail", &NTPinnerRtail);
    t->Branch("InnerEventTime", &NTPinnerEventTime);

    t->Branch("VetopC", &NTPvetopC);
    t->Branch("VetoPanel", &NTPvetoPanel);
    t->Branch("VetoEventTime", &NTPvetoEventTime);

    return;
} 

void initializing_out(){
    
    NTPtrgNumber = 0;
    NTPeventType = -99;
    
    NTPinnerNPE = -99;
    NTPinnerRtail = -99;
    NTPinnerEventTime = -99;
    
    NTPvetopC.clear();
    NTPvetoPanel.clear();
    NTPvetoEventTime.clear();



    return;
}


// - Time - //
void F_WaveStartTimeCorrection(){

    cout<<"Prev T = "<<prev_FstartTime[0]<<", Curr T = "<<FstartTime[0]<<endl;
    for( int ich = 0; ich < nchFADC; ich++ ){
    
        if( FstartTime[ich] - prev_FstartTime[ich] < 0 ) { F_numCycle[ich]++; }
        prev_FstartTime[ich] = FstartTime[ich];

        FstartTime[ich] = FstartTime[ich] + F_numCycle[ich] * (double)TimeConst;

    }

    return;

}

void S_WaveStartTimeCorrection(){

    for( int ich = 0; ich < nchSADC; ich++ ){

        if( SstartTime[ich] - prev_SstartTime[ich] < 0 ) { S_numCycle[ich]++; }
        prev_SstartTime[ich] = SstartTime[ich];

        SstartTime[ich] = SstartTime[ich] + S_numCycle[ich] * (double)TimeConst;

    }

    return;

}

int FindFastTime_FADC(std::vector<int> fb){

    int targetBin = 0;

    int b = fb.size();
    for( int i = 0; i < b; i++ ){ 

        if( i == 0 ) { targetBin = fb.at(i); }
        else { targetBin = targetBin < fb.at(i) ? targetBin : fb.at(i); }
    
    }

    return targetBin;

}

double FindFastTime_SADC(std::vector<double> fb){

    double targetTime = 0;

    int b = fb.size();
    for( int i = 0; i < b; i++ ){ 

        if( i == 0 ) { targetTime = fb.at(i); }
        else { targetTime = targetTime < fb.at(i) ? targetTime : fb.at(i); }
    
    }

    return targetTime;

}

#endif
