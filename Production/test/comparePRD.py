#!/usr/bin/env python
import sys
import os
import argparse
import uproot
import numpy as np

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f'{sys.argv[0]}: Compare input trees')
    parser.add_argument('file1', type=str, help='File1')
    parser.add_argument('file2', type=str, help='File2')
    parser.add_argument('-t', '--tree-name', type=str, default='Event', help='TTree name')
    parser.add_argument('-k', '--skip-missing', action=argparse.BooleanOptionalAction, default=True, help='Skip missing branch')
    parser.add_argument('-q', '--error-only', action=argparse.BooleanOptionalAction, default=False, help='Print errors only')
    args = parser.parse_args()

    fName1, fName2 = args.file1, args.file2
    tName = args.tree_name

    if not args.error_only:
        print(f"{os.path.basename(sys.argv[0])}: Compare flat trees in two input ROOT files")
        print(f"  File1 = {fName1}")
        print(f"  File2 = {fName2}")
        print()

    ## Open files
    f1 = uproot.open(fName1)
    f2 = uproot.open(fName2)
    t1 = f1[tName]
    t2 = f2[tName]

    if t1 is None or t2 is None:
        print(f"\u274C\nERROR: Invalid TTree...", end='')
        if t1 is None: print(f"in {fName1}")
        if t2 is None: print(f"in {fName2}")
        print()
        sys.exit(1)

    if not args.error_only:
        print(f"Checking branch names... ", end="")
    bNames1, bNames2 = t1.keys(), t2.keys()
    if set(bNames1) == set(bNames2):
        if not args.error_only:
            print(f"\u2705 OK, nBranches={len(bNames1)}")
    else:
        if not args.skip_missing:
            print(f"\n\u274C\nERROR: Different branch names!!!")
            print(f"         b1={bNames1}")
            print(f"         b2={bNames2}")
            sys.exit(1)
    bNames = set(bNames1).intersection(bNames2)

    if not args.error_only:
        print(f"Checking number of events... ", end="")
    n1, n2 = t1.num_entries, t2.num_entries
    if n1 == n2:
        if not args.error_only:
            print(f"\u2705 OK, n={n1}")
    else:
        print(f"\n\u274C\nERROR: Different entries n1={n1}, n2={n2}")
        sys.exit(2)

    diffCode = 0
    if not args.error_only:
        print(f"Checking branch contents one by one...")
    for bName in bNames:
        if not args.error_only:
            print(f"Checking branch \"{bName}\"...", end="")
        arr1 = t1[bName].array(library='np')
        arr2 = t2[bName].array(library='np')
        if arr1.shape != arr2.shape:
            print(f"\u274C\nERROR: Different shape! arr1={arr1.shape} arr2={arr2.shape}")
            diffCode = 3
            continue
        if arr1.dtype != arr2.dtype:
            print(f"\u274C\nERROR: Different object type! arr1={arr1.dtype} arr2={arr2.dtype}", end='')
            #continue

        if arr1.dtype == object:
            arr1 = np.stack(arr1)
        if arr2.dtype == object:
            arr2 = np.stack(arr2)

        diff_mask = (arr1 != arr2)
        if diff_mask.sum() > 0:
            print(f"\u274C\nERROR: Different content! nDiff={diff_mask.sum()}")
            print(f"  different contents in arr1: {arr1[diff_mask]}")
            print(f"  different contents in arr2: {arr2[diff_mask]}")
            diffCode = 4
            continue

        if not args.error_only:
            print(f"\u2705")

    sys.exit(diffCode)
