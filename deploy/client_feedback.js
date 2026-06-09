/**
 * Submit feedback to ERC-8004 ReputationRegistry FROM A CLIENT WALLET.
 *
 * The service owner (0x0eF0Fa79...) CANNOT give self-feedback.
 * This script is called from a SEPARATE client wallet — an AI agent that
 * used the BacktestStrategyAgent service and is now rating it on-chain.
 *
 * Usage:
 *   cd deploy
 *   CLIENT_PRIVATE_KEY=0x<client_key> node client_feedback.js
 *
 * Requirements:
 *   - CLIENT_PRIVATE_KEY wallet must have MNT on Mantle Mainnet for gas
 *   - This is NOT the owner wallet (0x0eF0Fa79...)
 *
 * Saves result to deploy/deployment.json under key "reputation_client_feedback".
 */

const { ethers } = require("ethers");
const fs   = require("fs");
const path = require("path");

const MAINNET_RPC          = "https://rpc.mantle.xyz";
const REPUTATION_REGISTRY  = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63";
const AGENT_ID             = 113;

const ABI = [
  "function giveFeedback(uint256 agentId, int128 value, uint8 valueDecimals, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash) external",
  "event NewFeedback(uint256 indexed agentId, address indexed clientAddress, uint64 feedbackIndex, int128 value, uint8 valueDecimals, string indexed indexedTag1, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)",
];

async function main() {
  const privateKey = process.env.CLIENT_PRIVATE_KEY;
  if (!privateKey || privateKey === "0x...") {
    console.error("❌  Set CLIENT_PRIVATE_KEY env var (must be a CLIENT wallet, not the service owner)");
    process.exit(1);
  }

  const provider = new ethers.JsonRpcProvider(MAINNET_RPC);
  const wallet   = new ethers.Wallet(privateKey, provider);
  const balance  = await provider.getBalance(wallet.address);

  console.log("=".repeat(60));
  console.log("  ERC-8004 ReputationRegistry — Client Feedback");
  console.log("=".repeat(60));
  console.log(`  Registry : ${REPUTATION_REGISTRY}`);
  console.log(`  AgentId  : ${AGENT_ID}  (BacktestStrategyAgent)`);
  console.log(`  Client   : ${wallet.address}`);
  console.log(`  Balance  : ${ethers.formatEther(balance)} MNT`);

  if (balance === 0n) {
    console.error("\n❌  Client wallet has 0 MNT. Top up with MNT on Mantle Mainnet for gas.");
    process.exit(1);
  }

  const registry = new ethers.Contract(REPUTATION_REGISTRY, ABI, wallet);

  const tx = await registry.giveFeedback(
    AGENT_ID,
    100,                         // value: int128, score 0–100
    0,                           // valueDecimals
    "backtest-service",          // tag1 — service category
    "algo-trading",              // tag2 — domain
    "https://alphaterminal.live/api/backtest",   // endpoint used
    "",                          // feedbackURI (empty for MVP)
    ethers.ZeroHash,             // feedbackHash (bytes32 zero)
  );

  console.log(`\n  Tx sent  : ${tx.hash}`);
  console.log("  Waiting for confirmation...");
  const receipt = await tx.wait();

  // Parse feedbackIndex from NewFeedback event
  let feedbackIndex = null;
  const iface = new ethers.Interface(ABI);
  for (const log of receipt.logs) {
    try {
      const parsed = iface.parseLog(log);
      if (parsed?.name === "NewFeedback") {
        feedbackIndex = parsed.args.feedbackIndex.toString();
        break;
      }
    } catch {}
  }

  console.log("\n  ✅  Feedback submitted!");
  console.log(`  feedbackIndex : ${feedbackIndex ?? "(check explorer)"}`);
  console.log(`  Block         : ${receipt.blockNumber}`);
  console.log(`  Explorer      : https://explorer.mantle.xyz/tx/${tx.hash}`);

  // Save to deployment.json
  const deployFile = path.join(__dirname, "deployment.json");
  let existing = {};
  try { existing = JSON.parse(fs.readFileSync(deployFile, "utf8")); } catch {}

  existing.reputation_client_feedback = {
    registry:      REPUTATION_REGISTRY,
    agentId:       AGENT_ID,
    clientWallet:  wallet.address,
    score:         100,
    tag1:          "backtest-service",
    tag2:          "algo-trading",
    feedbackIndex: feedbackIndex ? Number(feedbackIndex) : null,
    txHash:        tx.hash,
    blockNumber:   receipt.blockNumber,
    explorerUrl:   `https://explorer.mantle.xyz/tx/${tx.hash}`,
    submittedAt:   new Date().toISOString(),
  };

  fs.writeFileSync(deployFile, JSON.stringify(existing, null, 2));
  console.log("\n  Saved to deploy/deployment.json  (key: \"reputation_client_feedback\")");
  console.log();
}

main().catch(e => {
  console.error("❌  Error:", e.message || e);
  process.exit(1);
});
