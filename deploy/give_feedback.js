/**
 * Submit feedback to the official ERC-8004 ReputationRegistry on Mantle Mainnet.
 *
 * Usage:
 *   cd deploy
 *   PRIVATE_KEY=0x... node give_feedback.js
 *
 * Saves result to deploy/deployment.json under key "reputation_mainnet".
 */

const { ethers } = require("ethers");
const fs   = require("fs");
const path = require("path");

const MAINNET_RPC          = "https://rpc.mantle.xyz";
const REPUTATION_REGISTRY  = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63";
const AGENT_ID             = 113;

// Minimal ABI — only functions we call
const ABI = [
  "function giveFeedback(uint256 agentId, int128 value, uint8 valueDecimals, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash) external",
  "event NewFeedback(uint256 indexed agentId, address indexed clientAddress, uint64 feedbackIndex, int128 value, uint8 valueDecimals, string indexed indexedTag1, string tag1, string tag2, string endpoint, string feedbackURI, bytes32 feedbackHash)",
];

// ── Feedback params ───────────────────────────────────────────────────────────
// value: 0–100 score (int128, valueDecimals=0)
// tag1 / tag2: categorization (indexed in contract)
// endpoint: the service URL being evaluated
// feedbackURI: pointer to detailed feedback data
// feedbackHash: keccak256 of feedback content for on-chain integrity
const FEEDBACK = {
  value:         90,                              // score: 90/100 — excellent
  valueDecimals: 0,
  tag1:          "backtest-accuracy",
  tag2:          "algo-trading",
  endpoint:      "https://alphaterminal.live/api/backtest",
  feedbackURI:   "https://alphaterminal.live/agent-card.json",
  description:   "BacktestStrategyAgent: 7 strategies, x402 pay-per-use, Bybit Futures data up to 180d. Accurate backtests with USDT metrics, Sharpe ratio, equity curve.",
};

async function main() {
  const privateKey = process.env.PRIVATE_KEY;
  if (!privateKey || privateKey === "0x...") {
    console.error("❌  Set PRIVATE_KEY env var");
    process.exit(1);
  }

  const provider = new ethers.JsonRpcProvider(MAINNET_RPC);
  const wallet   = new ethers.Wallet(privateKey, provider);
  const balance  = await provider.getBalance(wallet.address);

  console.log("=".repeat(60));
  console.log("  ERC-8004 ReputationRegistry — Give Feedback");
  console.log("=".repeat(60));
  console.log(`  Registry : ${REPUTATION_REGISTRY}`);
  console.log(`  AgentId  : ${AGENT_ID}`);
  console.log(`  Score    : ${FEEDBACK.value}/100`);
  console.log(`  Tag1     : ${FEEDBACK.tag1}`);
  console.log(`  Tag2     : ${FEEDBACK.tag2}`);
  console.log(`  Wallet   : ${wallet.address}`);
  console.log(`  Balance  : ${ethers.formatEther(balance)} MNT`);

  if (balance === 0n) {
    console.error("\n❌  Wallet has 0 MNT. Cannot pay gas.");
    process.exit(1);
  }

  // feedbackHash = keccak256(description) — proves content integrity on-chain
  const feedbackHash = ethers.keccak256(ethers.toUtf8Bytes(FEEDBACK.description));

  const registry = new ethers.Contract(REPUTATION_REGISTRY, ABI, wallet);

  console.log("\n  Sending giveFeedback() transaction...");
  const tx = await registry.giveFeedback(
    AGENT_ID,
    FEEDBACK.value,
    FEEDBACK.valueDecimals,
    FEEDBACK.tag1,
    FEEDBACK.tag2,
    FEEDBACK.endpoint,
    FEEDBACK.feedbackURI,
    feedbackHash,
  );

  console.log(`  Tx sent  : ${tx.hash}`);
  console.log("  Waiting for confirmation...");
  const receipt = await tx.wait();

  // Parse feedbackIndex from NewFeedback event
  let feedbackIndex = null;
  const iface = new ethers.Interface(ABI);
  for (const log of receipt.logs) {
    try {
      const parsed = iface.parseLog(log);
      if (parsed && parsed.name === "NewFeedback") {
        feedbackIndex = parsed.args.feedbackIndex.toString();
        break;
      }
    } catch {}
  }

  console.log("\n  ✅  Feedback submitted!");
  console.log(`  feedbackIndex : ${feedbackIndex ?? "(check explorer)"}`);
  console.log(`  Block         : ${receipt.blockNumber}`);
  console.log(`  Explorer      : https://explorer.mantle.xyz/tx/${tx.hash}`);

  // ── Save to deployment.json ──────────────────────────────────────────────
  const deployFile = path.join(__dirname, "deployment.json");
  let existing = {};
  try { existing = JSON.parse(fs.readFileSync(deployFile, "utf8")); } catch {}

  existing.reputation_mainnet = {
    registry:      REPUTATION_REGISTRY,
    agentId:       AGENT_ID,
    score:         FEEDBACK.value,
    tag1:          FEEDBACK.tag1,
    tag2:          FEEDBACK.tag2,
    feedbackIndex: feedbackIndex ? Number(feedbackIndex) : null,
    txHash:        tx.hash,
    blockNumber:   receipt.blockNumber,
    explorerUrl:   `https://explorer.mantle.xyz/tx/${tx.hash}`,
    submittedAt:   new Date().toISOString(),
  };

  fs.writeFileSync(deployFile, JSON.stringify(existing, null, 2));
  console.log("\n  Saved to deploy/deployment.json  (key: \"reputation_mainnet\")");
  console.log();
}

main().catch(e => {
  console.error("❌  Error:", e.message || e);
  process.exit(1);
});
