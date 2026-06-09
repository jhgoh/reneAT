#!/usr/bin/env python
import os
import gzip
import numpy as np

class RunInfo:
    def __init__(self, runNumber, dictFADC, dictSADC):
        nF, nS = 0, 0
        for key, value in dictFADC.items():
            if key == 'NADC': continue
            setattr(self, f"F_{key}", np.array(value, dtype=np.int32))
            nF = len(value)
        for key, value in dictSADC.items():
            if key == 'NADC': continue
            setattr(self, f"S_{key}", np.array(value, dtype=np.int32))
            nS = len(value)

        self.runNumber = np.array([runNumber], dtype=np.uint32)
        self.nF = np.array([nF], dtype=np.int32)
        self.nS = np.array([nS], dtype=np.int32)

class TCBLogReader:
    def __init__(self, runNumber):
        fName = f"TCBLOG/TCB_{runNumber:06}.log"
        f = None
        if os.path.exists(fName):
            f = open(fName)
        elif os.path.exists(fName+".gz"):
            f = gzip.open(f"TCBLOG/TCB_{runNumber:06}.log.gz", 'rt')

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
    reader = TCBLogReader(4000)
    infoFADC, infoSADC = reader.ExtractWJ()
    print("--------- FADC info ---------")
    print(infoFADC)
    print("--------- SADC info ---------")
    print(infoSADC)
    
