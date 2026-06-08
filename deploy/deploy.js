/**
 * Deploy BacktestAgentRegistry to Mantle (testnet or mainnet).
 * Usage:
 *   npm install ethers
 *   PRIVATE_KEY=0x... RPC_URL=https://rpc.sepolia.mantle.xyz node deploy.js
 *   # For mainnet:
 *   PRIVATE_KEY=0x... RPC_URL=https://rpc.mantle.xyz node deploy.js
 */

const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

const ABI_PATH = path.join(__dirname, "../contracts/abi/BacktestAgentRegistry.json");

async function main() {
  const rpcUrl = process.env.RPC_URL || "https://rpc.sepolia.mantle.xyz";
  const privateKey = process.env.PRIVATE_KEY;

  if (!privateKey) {
    console.error("Set PRIVATE_KEY env var");
    process.exit(1);
  }

  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(privateKey, provider);

  console.log("Deploying from:", wallet.address);
  console.log("Network:", rpcUrl);

  const { abi, bytecode } = JSON.parse(fs.readFileSync(ABI_PATH, "utf8"));
  const factory = new ethers.ContractFactory(abi, bytecode, wallet);

  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("BacktestAgentRegistry deployed at:", address);

  // Register the agent
  const METADATA_URI = process.env.METADATA_URI || "https://alphaterminal.live/agent-card.json";
  const tx = await contract.registerAgent(
    "BacktestStrategyAgent",
    "AI-powered backtesting agent for crypto trading strategies on Bybit Futures. Pay-per-use via x402 on Mantle.",
    METADATA_URI,
    "https://alphaterminal.live",
    true
  );
  const receipt = await tx.wait();

  // Get agentId from event
  const event = receipt.logs
    .map(log => { try { return contract.interface.parseLog(log); } catch { return null; } })
    .find(e => e && e.name === "AgentRegistered");

  const agentId = event?.args?.agentId;
  console.log("Agent registered! agentId:", agentId);

  const out = { contractAddress: address, agentId, network: rpcUrl, deployer: wallet.address };
  fs.writeFileSync(path.join(__dirname, "deployment.json"), JSON.stringify(out, null, 2));
  console.log("Saved to deploy/deployment.json");
}

main().catch(console.error);
