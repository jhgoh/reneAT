
void hist_label_format(TH1D* h){

    h->GetXaxis()->CenterTitle(true);                      
    h->GetXaxis()->SetLabelFont(72);                       
    h->GetXaxis()->SetTitleFont(72);                       
    h->GetYaxis()->CenterTitle(true);                      
    h->GetYaxis()->SetLabelFont(72);                       
    h->GetYaxis()->SetTitleFont(72);

}

void graph_label_format(TGraph* g){

    g->GetXaxis()->CenterTitle(true);                      
    g->GetXaxis()->SetLabelFont(72);                       
    g->GetXaxis()->SetTitleFont(72);                       
    g->GetYaxis()->CenterTitle(true);                      
    g->GetYaxis()->SetLabelFont(72);                       
    g->GetYaxis()->SetTitleFont(72);

}
