//
// -----------------------
// Charge Summation class.
// -----------------------
//
// wrote by WJ Lee.
//

#include "../include/ChargeSum.hh"


// Calculation
double ChargeSum::ChargeSummation(int range1, int range2){

    double chargeSum = 0;

    int b = Wave_->size();
    for(int i=range1; i<range2; i++){

        double q = Wave_->at(i) - Pedestal;

        chargeSum += q;

    }

    return chargeSum;

}

double ChargeSum::PedestalCal(int range1, int range2){

    double ped = 0;

    int b = Wave_->size();
    for(int i=range1; i<range2; i++){

        double q = Wave_->at(i);

        ped += q;

    }

    return (double)ped / (range2 - range1);

}

double ChargeSum::PedestalStab_RMS(int range1, int range2){

    double rms = 0;

    if( Pedestal == 0 ) { this->SetPed(range1, range2); }


    int b = Wave_->size();
    for(int i=range1; i<range2; i++){

        double q = Wave_->at(i);

        rms += (q - Pedestal) * (q - Pedestal);

    }


    return sqrt( (double)rms / (range2 - range1) );

}

// Setting
void ChargeSum::SetQsum(int range1, int range2){

    this->Qsum = this->ChargeSum::ChargeSummation(range1, range2);

    return;

}

void ChargeSum::SetPed(int range1, int range2){

    this->Pedestal = this->ChargeSum::PedestalCal(range1, range2);

    return;

}

void ChargeSum::SetQtail(int range1, int range2){ 

    this->Qtail = this->ChargeSum::ChargeSummation(range1, range2);

    return;

}

/*void ChargeSum::SetTmean(int range1, int range2){ // require the sync waveform
// 2024.08.08 I don't know the def of Tmean exactly, so I just made an average! need to be corrected

    double chargeSumT = 0;
    double chargeSum = 0;

    int b = Wave_->size();
    for(int i=range1; i<range2; i++){

        double q = Wave_->at(i) - Pedestal;

        chargeSumT = chargeSumT + q*;
        chargeSum += q;

    }

    this->Tmean = (double)chargeSumT / chargeSum;

    return; (double) chargeSum;

}*/

// Noise removal
bool ChargeSum::NoiseFiltering(int p, int ref){

    bool flag = false;

    int b = Wave_->size();
    //cout<<"ped = "<<p<<", ref = "<<ref<<", size = "<<b<<endl;
    for(int i=0; i<b; i++){

        if( (Wave_->at(i) - p) < ((-1) * ref) ){ flag = true; }

        if( flag ) break;

    }

    return flag;

}

// Find the fired bin (1st one)
int ChargeSum::FiredBin(){

    int targetBin = -99;

    int b = Wave_->size();

    for(int i=0; i<b; i++){

        if( Wave_->at(i) - Pedestal >= Threshold ){
            targetBin = i; break;
        }

    }


    return targetBin;

}

// Change the threshold for the analysis
bool ChargeSum::ThresholdControl(int p, int ref){

    bool flag = true;

    int b = Wave_->size();
    for(int i=0; i<b; i++){

        //if( (Wave_->at(i) - p) >= ref ){cout<<"Wave_->at(i) = "<<Wave_->at(i)<<", p = "<<p<<", ref = "<<ref<<", diff = "<<(Wave_->at(i) - p)<<endl;}

        if( (Wave_->at(i) - p) >= ref ){ flag = false; }

        if( !flag ) break;

    }

    return flag;

}
