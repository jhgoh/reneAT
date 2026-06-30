#!/usr/bin/env python
import os
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

    def GetDict(self):
        return {attr: getattr(self, attr).tolist()
                for attr in vars(self)
                if attr.startswith(('F_', 'S_'))}

