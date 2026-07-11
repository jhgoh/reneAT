#ifndef WAVE_HH
#define WAVE_HH 

#include <vector>
#include "../include/ChargeSum.hh"


using namespace std;

class Wave{

    // functions
    public:
        Wave(): cs_container(0), wave_container(0) {};
        ~Wave(){
            cs_container.clear(); 
            wave_container.clear();

            firedbins.clear();
            delete Wave_tot;
        }


        void ChargeSumContainer(ChargeSum* );

        // Use the functions after calling "void ChargeSumContainer(ChargeSum* );"
        // Also, Set000 functions of ChargeSum class need to be called in the main code in advance!
        vector<vector<unsigned short>*> AlignWaveform(int ); // OnOff_shift
        vector<unsigned short>* AddWaveforms(vector<vector<unsigned short>*>); // wave_container


        vector<vector<unsigned short>*> GetWaveContainer() { return wave_container; }
        vector<ChargeSum*> GetCSContainer() { return cs_container; }
        vector<unsigned short>* GetSummedWave(){ return Wave_tot; }

        void SetSummedWave(vector<unsigned short>* );

        vector<int> GetFiredBins() { return firedbins; } // must be called after "AlignWaveform"


    // variables
    protected:
        vector<ChargeSum*> cs_container;

        vector<vector<unsigned short>*> wave_container;

        int ref_firedbin = 110; // Hardcode!: position where waves are placed in sample axis.
        vector<int> firedbins;

        vector<unsigned short>* Wave_tot;



};


#endif
