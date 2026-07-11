#ifndef SADC_HH
#define SADC_HH 

#include <iostream>
#include <vector>
#include <tuple>
#include <algorithm>


using namespace std;

class SADC{

    public:
        SADC() {};
        ~SADC(){
            sadc_tuple.clear();
        }

        void Add(int /*ch*/, int /*vetoPanel*/, double /*adc*/, double /*starttime*/, double /*peaktime*/);

        vector<tuple<int, int, double, double, double>> GetTuple(){
            return this->sadc_tuple;
        }

        void SortingByTime();


    protected:
        vector<tuple<int, int, double, double, double>> sadc_tuple;




};




#endif
