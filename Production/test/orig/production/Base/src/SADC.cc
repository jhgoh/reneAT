//
// -----------------------
// SADC class.
// -----------------------
//
// wrote by WJ Lee.
//

#include "../include/SADC.hh"


void SADC::Add(int ch, int vetoPanel, double adc, double starttime, double peaktime){

    this->sadc_tuple.push_back(make_tuple(ch, vetoPanel, adc, starttime, peaktime));

    return;

}


bool compareAscending(tuple<int, int, double, double, double> x1, 
                      tuple<int, int, double, double, double> x2){
    return ( std::get<4>(x1) < std::get<4>(x2) ); // ascending order
}

void SADC::SortingByTime(){
    
    sort(this->sadc_tuple.begin(), this->sadc_tuple.end(), compareAscending);

    return;

}

