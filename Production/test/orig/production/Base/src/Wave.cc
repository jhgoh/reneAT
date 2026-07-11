//
// -----------------------
// Wave class.
// -----------------------
//
// wrote by WJ Lee.
//

#include "../include/Wave.hh"


void Wave::ChargeSumContainer(ChargeSum* cs){

    this->cs_container.push_back(cs);

    return;

}

vector<vector<unsigned short>*> Wave::AlignWaveform(int OnOff){

    vector<vector<unsigned short>*> wc;


    int b = this->cs_container.size();
    for( int i = 0; i < b; i++ ){
    
        this->firedbins.push_back(this->cs_container.at(i)->FiredBin());

        vector<unsigned short>* w = new vector<unsigned short>;

        ChargeSum* cs = (ChargeSum*)this->cs_container.at(i);

        int bb = cs->GetWave()->size();
        int bindiff = (OnOff == 1) ? this->firedbins.at(i) - this->ref_firedbin : 0; //
        for( int j = 0; j < bb; j++ ){

            unsigned short val = 0;
            if( j+bindiff >= 0 && j+bindiff < bb ) { val = cs->GetWave()->at(j+bindiff); }
            else { val = cs->GetPed(); }

            w->push_back(val);

        }

        wc.push_back(w);
        //delete w;

    }

    this->wave_container = wc;

    return wc;

}

vector<unsigned short>* Wave::AddWaveforms(vector<vector<unsigned short>*> wcaligned){

    vector<unsigned short>* wtot = new vector<unsigned short>;

    int bb = wcaligned.at(0)->size();
    for( int j = 0; j < bb; j++ ){

        unsigned short val = 0;

        int b = wcaligned.size();
        for( int i = 0; i < b; i++ ){

            val += wcaligned.at(i)->at(j);

        }
         
        wtot->push_back(val);

    }


    return wtot;

}

void Wave::SetSummedWave(vector<unsigned short>* w){

    this->Wave_tot = w;

    return;

}
