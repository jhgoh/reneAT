#!/usr/bin/env python3
import sys
import os
import argparse
import yaml

sys.path.append('python')
from logreader import parseConfig, parseDAQSummary, parseTCBLog

parser = argparse.ArgumentParser(description='Generate runInfo YAML from CONFIG + DAQ logs')
parser.add_argument('runNumber', type=int)
parser.add_argument('--out', default='.', help='Output directory (default: current dir)')
parser.add_argument('--config-dir', default='CONFIG')
parser.add_argument('--daqlog-dir', default='DAQLOG')
args = parser.parse_args()

runNumber = args.runNumber
cfg  = parseConfig(f"{args.config_dir}/{runNumber:06d}.config")
logT = parseTCBLog(f"{args.daqlog_dir}/TCB/TCB_{runNumber:06d}.log.gz")
logF = parseDAQSummary(f"{args.daqlog_dir}/FADCDAQ/FADCDAQ_{runNumber:06d}.log.gz")
logS = parseDAQSummary(f"{args.daqlog_dir}/SADCDAQ/SADCDAQ_{runNumber:06d}.log.gz")

fadc_reg = (logT or {}).get('FADC register', {})
sadc_reg = (logT or {}).get('SADCT register', {})
summary  = logF or logS or {}
tcb_cfg  = (cfg or {}).get('TCB', {})
fadc_cfg = (cfg or {}).get('FADCT', {})
sadc_cfg = (cfg or {}).get('SADCT', {})

runInfo = {
    'run': {
        'runNumber':   runNumber,
        'startTime':   summary.get('Start Time'),
        'endTime':     summary.get('End Time'),
        'liveTime':    summary.get('Live time'),
        'triggerRate': summary.get('Trigger rate'),
        'nEvents':     int(summary['Total number of event']) if 'Total number of event' in summary else None,
    },
    'TCB': {
        'type':  tcb_cfg.get('TYPE'),
        'cw':    tcb_cfg.get('CW'),
        'pTrig': tcb_cfg.get('PTRIG'),
    },
    'FADC': {
        'recordLength': fadc_reg.get('RL') or fadc_cfg.get('RL'),
        'tlt':          fadc_reg.get('TLT'),
        'channels': {
            'id':        fadc_reg.get('CID'),
            'pmtId':     fadc_cfg.get('PID'),
            'threshold': fadc_reg.get('THR'),
            'delay':     fadc_reg.get('DLY'),
            'cw':        fadc_reg.get('CW'),
        },
    },
    'SADC': {
        'gw': sadc_reg.get('GW'),
        'cw': sadc_reg.get('CW'),
        'channels': {
            'id':        sadc_reg.get('CID'),
            'pmtId':     sadc_cfg.get('PID'),
            'threshold': sadc_reg.get('THR'),
            'delay':     sadc_reg.get('DLY'),
        },
    },
}

yaml.add_representer(dict,
    lambda d, v: d.represent_mapping('tag:yaml.org,2002:map', v.items(), flow_style=False))

outPath = os.path.join(args.out, f"runInfo_{runNumber:06d}.yaml")
with open(outPath, 'w') as f:
    yaml.dump(runInfo, f, default_flow_style=None, sort_keys=False, allow_unicode=True)
print(f"Written: {outPath}")
