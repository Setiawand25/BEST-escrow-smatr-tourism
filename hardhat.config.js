require("@nomicfoundation/hardhat-ethers");
try { require("@nomicfoundation/hardhat-verify"); } catch (_) {}
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");
const path = require("path");

// Use the locally downloaded native solc 0.8.24 (no compiler download at build time).
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD, async (args, hre, runSuper) => {
  // use the bundled native solc only on Linux when present; elsewhere Hardhat downloads solc itself
  if (args.solcVersion === "0.8.24" && process.platform === "linux" && require("fs").existsSync(path.join(__dirname, "bin", "solc"))) {
    return { compilerPath: path.join(__dirname, "bin", "solc"), isSolcJs: false,
             version: "0.8.24", longVersion: "0.8.24+commit.e11b9ed9" };
  }
  return runSuper();
});

// DRYRUN=1 turns the in-process network into a Sepolia-like chain (chainId 11155111, one block every 12 s)
const DRY = process.env.DRYRUN === "1";
const keys = (process.env.SEPOLIA_PRIVATE_KEYS || process.env.SEPOLIA_PRIVATE_KEY || "").split(",").map(k => k.trim()).filter(Boolean);

module.exports = {
  solidity: { version: "0.8.24", settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "cancun" } },
  networks: {
    hardhat: DRY
      ? { hardfork: "cancun", chainId: 11155111, blockGasLimit: 60_000_000, accounts: { count: 20 }, mining: { auto: false, interval: 12_000 } }
      : { hardfork: "cancun", blockGasLimit: 60_000_000, accounts: { count: 60 } },
    // Real Sepolia: SEPOLIA_RPC_URL=https://... SEPOLIA_PRIVATE_KEYS=key_admin,key_platform,key_affiliate,key_sdg,key_hotel,key_guest1,...
    // local Sepolia-like node started with: DRYRUN=1 npx hardhat node
    localdry: { url: "http://127.0.0.1:8545", chainId: 11155111 },
    sepolia: { url: process.env.SEPOLIA_RPC_URL || "https://rpc.sepolia.org", chainId: 11155111, accounts: keys },
  },
  etherscan: { apiKey: process.env.ETHERSCAN_API_KEY || "" },
  sourcify: { enabled: true },
};
