#!/bin/bash
# Site-specific ROOT environment setup.
# Sourced by _remote scripts at startup — edit for your site.

if [ -d /cvmfs/sft.cern.ch/lcg/views ]; then
    # Detect OS and pick matching LCG view
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID-$VERSION_ID" in
            ubuntu-22.04) LCG_PLATFORM=x86_64-ubuntu2204-gcc11-opt ;;
            ubuntu-20.04) LCG_PLATFORM=x86_64-ubuntu2004-gcc9-opt  ;;
            rhel-9*|centos-9*|almalinux-9*|rocky-9*) LCG_PLATFORM=x86_64-el9-gcc13-opt  ;;
            rhel-8*|centos-8*|almalinux-8*|rocky-8*) LCG_PLATFORM=x86_64-centos8-gcc11-opt ;;
            *) echo "!!! Unsupported OS for LCG: $ID-$VERSION_ID" >&2; return 1 ;;
        esac
    else
        echo "!!! Cannot detect OS for LCG platform selection" >&2; return 1
    fi
    LCG_VIEW=/cvmfs/sft.cern.ch/lcg/views/LCG_106/${LCG_PLATFORM}
    source ${LCG_VIEW}/setup.sh

elif command -v mamba &>/dev/null; then
    eval "$(mamba shell hook --shell bash 2>/dev/null)" || { echo "!!! mamba shell hook failed" >&2; return 1; }
    mamba activate hep2026.01 || { echo "!!! mamba activate hep2026.01 failed" >&2; return 1; }

else
    echo "!!! No ROOT environment found (CVMFS LCG or mamba)" >&2
    return 1
fi
