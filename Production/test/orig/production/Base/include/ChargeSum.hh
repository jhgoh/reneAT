#ifndef CHARGESUM_HH
#define CHARGESUM_HH 

class ChargeSum{

    // functions
    public:
        ChargeSum() : Wave_(nullptr), Threshold(0), Qsum(0.0), Pedestal(0.0), Qtail(0.0) {};
        ~ChargeSum(){
            delete Wave_;
        }
       
        void SetQsum(int, int); // range1, range2
        void SetPed(int, int); // range1, range2
        void SetQtail(int, int); // range1, range2
        void SetTmean(int, int); // range1, range2

        void SetChargeSumClass(std::vector<unsigned short>* w, int t){ // waveform, threshold
            Wave_ = w;
            Threshold = t;
        }

        bool NoiseFiltering(int, int); // If the height of waveform is lower than ref val, then it will be removed
        bool ThresholdControl(int, int); // If anyone wants to change the threshold, especially higher one, use it.

        int FiredBin();
        
        double ChargeSummation(int, int); // range1, range2
        double PedestalCal(int, int); // range1, range2
        double PedestalStab_RMS(int, int); // range1, range2

        int GetTHR() { return Threshold; }
        double GetPed() { return Pedestal; }
        double GetQsum() { return Qsum; }
        double GetQtail() { return Qtail; }
        double GetTmean() { return Tmean; }

        std::vector<unsigned short>* GetWave() { return Wave_; }


    // variables
    protected:
        std::vector<unsigned short> * Wave_;
        
        int Threshold;
        
        double Qsum;
        double Pedestal;

        double Qtail;
        double Tmean;

};


#endif
