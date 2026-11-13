# Smart Tourism escrow — reference contracts, tests and simulations

Reproduces every number in Sections V-C and VIII of the manuscript.

## Requirements
Node 18+ and Python 3.10+ (numpy, scipy, matplotlib). Optional: slither-analyzer 0.11.6.

## Steps
```
npm install
# put a native solc 0.8.24 at bin/solc (e.g. solc-static-linux from the Solidity GitHub release)
npx hardhat compile
N=400 npx hardhat run scripts/measure.js        # gas per function, conservation check -> results/gas.json
npx hardhat run scripts/marginal_sdg.js         # marginal gas of the SDG share -> results/marginal_sdg.json
npx hardhat run scripts/negative_tests.js       # 18 state-machine / access-control tests
npx hardhat run scripts/reentrancy_test.js      # hostile-token reentrancy test
slither contracts/BookingEscrow.sol --solc bin/solc --solc-remaps "@openzeppelin/=node_modules/@openzeppelin/" --filter-paths node_modules
cd sim && python3 cost.py && python3 des.py     # H1, H3, sensitivity; H2 discrete-event simulation
```
All parameters are in `sim/params.py`; seeds are fixed in the scripts.
Contracts are research prototypes and have NOT been audited. Do not deploy with real funds.

## Testnet campaign (Sepolia) and human-evaluation pipeline
```
# real Sepolia
SEPOLIA_RPC_URL=... SEPOLIA_PRIVATE_KEYS=k_admin,k_platform,k_affiliate,k_sdg,k_hotel,k_guest1,... \
  N_BOOKINGS=50 LABEL=sepolia_run1 npx hardhat run scripts/sepolia_campaign.js --network sepolia
# free local dry run on a Sepolia-like chain (chainId 11155111, 12-s blocks)
DRYRUN=1 npx hardhat node &   # in another terminal
SKIP_FINALITY=1 LEAD_S=300 npx hardhat run scripts/sepolia_campaign.js --network localdry
# expert panel + survey analysis (data/ currently holds DUMMY data; replace, delete data/DUMMY_MARKER, re-run)
python3 sim/human_eval_dummy.py
```
results/dryrun_* and data/* are SIMULATED reference outputs, not research results.
test  