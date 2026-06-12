#!/usr/bin/env python
import sys, os
import gzip

class TCBLogReader:
    def __init__(self, runNumber):
        fName = f"TCBLOG/TCB_{runNumber:06}.log"
        if os.path.exists(fName):
            f = open(fName)
        elif os.path.exists(fName+".gz"):
            f = gzip.open(fName+".gz", 'rt')
        else:
            raise FileNotFoundError(f"TCB log file not found: {fName}[.gz]")

        self.lines = []
        for line in f:
            self.lines.append(str(line))

    def ExtractWJ(self):
        infoFADC = {}
        infoSADC = {}

        for line in self.lines:
            line = line.strip().split(' ', 2)
            if len(line) < 3: continue

            producer, catName = line[0], line[1]
            if producer != "WJ": continue
            if catName not in ("FADC", "SADC"): continue

            if '=' not in line[-1]: continue
            varName, values = line[-1].split('=', 2)
            varName = varName.strip()
            values = [int(x) for x in values.split()]

            if catName == 'FADC':
                infoFADC[varName.split()[0]] = values
            elif catName == 'SADC':
                infoSADC[varName.split()[0]] = values

        return infoFADC, infoSADC

if __name__ == '__main__':
    reader = TCBLogReader(int(sys.argv[1]))
    infoFADC, infoSADC = reader.ExtractWJ()
    print("--------- FADC info ---------")
    print(infoFADC)
    print("--------- SADC info ---------")
    print(infoSADC)
    
