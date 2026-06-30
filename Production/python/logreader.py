#!/usr/bin/env python
import os
import gzip
import re
import copy

def parseConfig(path):
    if not os.path.exists(path):
        return None

    config = {}

    catName = None
    for line in open(path).readlines():
        line = line.rstrip()
        if line == '' or line.lstrip()[0] == '#': continue

        if line[0] != ' ': ## Begin/End of config block
            if line.split()[0] == 'END':
                catName = None
            elif catName == None:
                catName = line.split()[0]
                config[catName] = {}
        else:
            items = line.lstrip().split(maxsplit=1)
            if len(items) != 2:
                print(f"ERROR: Parsing issue {items}")
                continue
            key, val = items
            comment = ''
            if '#' in val:
                val, comment = val.split('#', maxsplit=1)
                val = val.strip()
                #comment = [x.strip() for x in comment.split('#')]
            val = [int(x) if x.isnumeric() else x for x in val.split()]
            if len(val) == 1: val = val[0]
            config[catName][key] = copy.deepcopy(val)
    
    return config

def parseDAQSummary(path):
    ## Try to open the log file, support log.gz but also the default .log
    if not os.path.exists(path):
        return None
    f = gzip.open(path, 'rt') if path.endswith('.gz') else open(path)

    ## Scan log file from the behind to front because
    ## we only need the Summary at the end of the log file.
    summary = None
    isValid = False
    for line in reversed(f.readlines()):
        line = line.strip()
        if line == '': continue
        
        ## Signatures where the DAQ summary block ends/starts
        ## we open/close the summary dictionary
        if line == '*'*len(line):
            summary = {}
            continue
        elif '* DAQ Summary *' in line:
            if summary is not None: isValid = True
            break
        ## Otherwise, just fill up the dictionary.
        key, val = line.split(':', 1)
        if summary is not None:
            summary[key.strip()] = val.strip()

    ## Invalidate if we could not meet DAQ Summary block title
    if not isValid:
        summary = None

    return summary

def parseTCBLog(path):
    catNamesToKeep = ["FADC register", "SADCT register"]
    config = {}

    ## Try to open the log file, support log.gz but also the default .log
    if not os.path.exists(path):
        return None
    f = gzip.open(path, 'rt') if path.endswith('.gz') else open(path)

    ## Scan the log file, we keep the key:values in two different formats,
    ## " ++ CATEGORY config/register: VAR1(VAL) VAR2(VAL) ..."
    ## "                              VAR3(VAL) VAR4(VAL) ..."
    ## or, " VAR1 : VAL1 VAL2 VAL3 ..." after the '-------' line.
    bufCatName, buffer = None, None
    isEoT, isEoL = True, True
    for line in f.readlines():
        line = line.rstrip()
        if line.strip() == '' or '[INFO]' in line: continue

        ## Signature that a block begins
        if line.startswith(' ++ ') and ':' in line:
            catName, vals = [x.strip() for x in line[4:].split(':',1)]
            if catName not in catNamesToKeep: continue

            ## Buffer already exists. Finalize existing one.
            if buffer is not None:
                config[bufCatName] = copy.deepcopy(buffer)
                bufCatName, buffer = None, None

            ## Create new buffer dict
            bufCatName, buffer = catName, {}
            for m in re.finditer(r'(\w+)\(([^)]+)\)', vals):
                key, val = m.group(1), m.group(2)
                buffer[key] = int(val) if val.isnumeric() else val
                isEoL = False
            continue
        ## Continue input when the line is not finished yet
        elif not isEoL and line.startswith('    '):
            for m in re.finditer(r'(\w+)\(([^)]+)\)', line):
                key, val = m.group(1), m.group(2)
                buffer[key] = int(val) if val.isnumeric() else val
            continue
        ## If we arrive here, we can assume the header of the block is done.
        isEoL = True
        
        ## Signature that a table begins/ends
        if line.strip() == '-'*len(line.strip()):
            isEoT = (not isEoT)

            ## Table is done. Finalize existing one.
            if isEoT and buffer is not None:
                config[bufCatName] = copy.deepcopy(buffer)
                bufCatName, buffer = None, None

            continue

        ## Fill the table row
        if buffer is not None and not isEoT and ':' in line:
            key, val = line.split(':', 1)
            key, val = key.strip(), val.strip()
            val = [int(x) for x in val.split()]
            buffer[key] = val
    if buffer is not None:
        config[bufCatName] = copy.deepcopy(buffer)
        bufCatName, buffer = None, None

    return config
