#!/usr/bin/env python
import sys, os
import uproot
import numpy as np

fName1 = sys.argv[1]
fName2 = sys.argv[2]
tName = "Event" if len(sys.argv) <= 3 else sys.argv[3]

print(f"{os.path.basename(sys.argv[0])}: Compare flat trees in two input ROOT files")
print(f"  File1 = {fName1}")
print(f"  File2 = {fName2}")
print(f"")

## Open files
f1 = uproot.open(fName1)
f2 = uproot.open(fName2)
t1 = f1[tName]
t2 = f2[tName]

if t1 == None or t2 == None:
    print(f"\u274C\nERROR: Invalid TTree...", end='')
    if t1 == None: print(f"in {fName1}")
    if t2 == None: print(f"in {fName2}")
    print()
    sys.exit(1)

print(f"Checking branch names... ", end="")
bNames1, bNames2 = t1.keys(), t2.keys()
if set(bNames1) == set(bNames2):
    print(f"\u2705 OK, nBranches={len(bNames1)}")
else:
    print(f"\n\u274C\nERROR: Diffrent branch names!!!")
    print(f"         b1={bNames1}")
    print(f"         b1={bNames2}")
    sys.exit(1)

print(f"Checking number of events... ", end="")
n1, n2 = t1.num_entries, t2.num_entries
if n1 == n2:
    print(f"\u2705 OK, n={n1}")
else:
    print(f"\n\u274C\nERROR: Different entries n1={n1}, n2={n2}")
    sys.exit(2)

print(f"Checking branch contents one by one...")
for bName in bNames1:
    print(f"Checking branch \"{bName}\"...", end="")
    arr1 = t1[bName].array(library='np')
    arr2 = t2[bName].array(library='np')
    if arr1.shape != arr2.shape:
        print(f"\u274C\nERROR: Different shape! arr1={arr1.shape} arr2={arr2.shape}")
        continue
    if arr1.dtype != arr2.dtype:
        print(f"\u274C\nERROR: Different object type! arr1={arr1.dtype} arr2={arr2.dtype}", end='')
        #continue

    if arr1.dtype == object:
        arr1 = np.stack(arr1)
    if arr2.dtype == object:
        arr2 = np.stack(arr2)

    diff_mask = (arr1 != arr2).any(axis=0)
    if diff_mask.sum() > 0:
        print(f"\u274C\nERROR: Different content! nDiff={diff_mask.sum()}")
        continue

    print(f"\u2705")

