/**
 * Register BacktestStrategyAgent in the official ERC-8004 IdentityRegistry on Mantle.
 *
 * Usage:
 *   npm install ethers          (already installed if you ran deploy.js before)
 *   cd deploy
 *
 *   # Testnet (default, safe to test):
 *   PRIVATE_KEY=0x... node register_official.js
 *
 *   # Mainnet (after testnet success):
 *   PRIVATE_KEY=0x... node register_official.js --mainnet
 *
 *   # With custom IPFS URI (after uploading to Pinata / web3.storage):
 *   PRIVATE_KEY=0x... AGENT_URI=ipfs://QmXxx... node register_official.js
 *
 * Output: saves agentId to deploy/deployment.json
 */

const { ethers } = require("ethers");
const fs   = require("fs");
const path = require("path");

// ── Official ERC-8004 singleton addresses ─────────────────────────────────────
const NETWORKS = {
  testnet: {
    name:     "Mantle Sepolia",
    chainId:  5003,
    rpc:      "https://rpc.sepolia.mantle.xyz",
    explorer: "https://explorer.sepolia.mantle.xyz/tx/",
    identity: "0x8004A818BFB912233c491871b3d84c89A494BD9e",
  },
  mainnet: {
    name:     "Mantle Mainnet",
    chainId:  5000,
    rpc:      "https://rpc.mantle.xyz",
    explorer: "https://explorer.mantle.xyz/tx/",
    identity: "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  },
};

// ── Agent Card URI ────────────────────────────────────────────────────────────
// Default: live HTTPS (valid per ERC-8004 spec).
// For IPFS permanence, upload agent-card.json to Pinata/web3.storage first:
//   npx w3 up frontend/agent-card.json        (web3.storage)
//   Then set: AGENT_URI=ipfs://Qm...
const AGENT_URI = process.env.AGENT_URI || "https://alphaterminal.live/agent-card.json";

// ── Minimal ABI ───────────────────────────────────────────────────────────────
// Full ABI: https://raw.githubusercontent.com/erc-8004/erc-8004-contracts/master/abis/IdentityRegistry.json
const ABI = [
  "function register(string memory agentURI) returns (uint256 agentId)",
  "function register() returns (uint256 agentId)",
];

// ERC-721 Transfer event — emitted on mint, topic[3] = tokenId = agentId
const TRANSFER_TOPIC = ethers.id("Transfer(address,address,uint256)");
const ZERO_ADDR_PADDED = "0x" + "0".repeat(64);

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const isMainnet = process.argv.includes("--mainnet");
  const net = isMainnet ? NETWORKS.mainnet : NETWORKS.testnet;

  const privateKey = process.env.PRIVATE_KEY;
  if (!privateKey || privateKey === "0x...") {
    console.error("❌  Set PRIVATE_KEY env var (e.g. PRIVATE_KEY=0x...)");
    process.exit(1);
  }

  console.log("=".repeat(60));
  console.log("  ERC-8004 IdentityRegistry — Agent Registration");
  console.log("=".repeat(60));
  console.log(`  Network   : ${net.name} (chainId ${net.chainId})`);
  console.log(`  Registry  : ${net.identity}`);
  console.log(`  Agent URI : ${AGENT_URI}`);
  console.log();

  const provider = new ethers.JsonRpcProvider(net.rpc);
  const wallet   = new ethers.Wallet(privateKey, provider);
  const balance  = await provider.getBalance(wallet.address);

  console.log(`  Wallet    : ${wallet.address}`);
  console.log(`  Balance   : ${ethers.formatEther(balance)} MNT`);

  if (balance === 0n) {
    console.error("\n❌  Wallet has 0 MNT — cannot pay gas.");
    if (!isMainnet) console.error("     Get testnet MNT: https://faucet.sepolia.mantle.xyz");
    process.exit(1);
  }

  const registry = new ethers.Contract(net.identity, ABI, wallet);

  console.log("\n  Sending register() transaction...");
  const tx = await registry["register(string)"](AGENT_URI);
  console.log(`  Tx sent   : ${tx.hash}`);
  console.log("  Waiting for confirmation...");

  const receipt = await tx.wait();

  // Parse agentId from ERC-721 Transfer(from=0x0) mint event
  let agentId = null;
  for (const log of receipt.logs) {
    if (
      log.topics[0] === TRANSFER_TOPIC &&
      log.topics[1] === ZERO_ADDR_PADDED
    ) {
      agentId = BigInt(log.topics[3]).toString();
      break;
    }
  }

  console.log();
  console.log("  ✅  Registration successful!");
  console.log(`  agentId   : ${agentId}`);
  console.log(`  Block     : ${receipt.blockNumber}`);
  console.log(`  Explorer  : ${net.explorer}${tx.hash}`);

  // ── Save to deployment.json ──────────────────────────────────────────────
  const deployFile = path.join(__dirname, "deployment.json");
  let existing = {};
  try { existing = JSON.parse(fs.readFileSync(deployFile, "utf8")); } catch {}

  const key = `official_${isMainnet ? "mainnet" : "testnet"}`;
  existing[key] = {
    network:          net.name,
    chainId:          net.chainId,
    identityRegistry: net.identity,
    agentId,
    agentURI:         AGENT_URI,
    txHash:           tx.hash,
    blockNumber:      receipt.blockNumber,
    registeredAt:     new Date().toISOString(),
  };

  fs.writeFileSync(deployFile, JSON.stringify(existing, null, 2));
  console.log(`\n  Saved to deploy/deployment.json  (key: "${key}")`);
  console.log();
}

main().catch(err => {
  console.error("❌  Error:", err.message || err);
  process.exit(1);
});
