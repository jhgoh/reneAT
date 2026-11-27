# source this file:  source /path/to/reneAT/setup.sh
# Puts reneAT/python on PYTHONPATH and the `reneat` command on PATH.
# Activate an environment with uproot/awkward/numpy/matplotlib first (KHU: mamba activate hep2026.01).
_RENEAT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export PYTHONPATH=$_RENEAT/python${PYTHONPATH:+:$PYTHONPATH}
export PATH=$_RENEAT/bin:$PATH
unset _RENEAT
