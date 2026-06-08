// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * BacktestAgentRegistry — ERC-8004 compliant Identity + Reputation Registry
 * for BacktestStrategyAgent on Mantle.
 *
 * ERC-8004 spec: https://eips.ethereum.org/EIPS/eip-8004
 */
contract BacktestAgentRegistry {

    // ──────────────── Agent Identity ────────────────

    struct AgentCard {
        string name;
        string description;
        string metadataURI;   // IPFS or HTTPS URL to full Agent Card JSON
        string endpoint;      // web endpoint
        bool   x402Support;
        bool   active;
        address owner;
        uint256 registeredAt;
    }

    mapping(bytes32 => AgentCard) public agents;
    bytes32[] public agentIds;

    event AgentRegistered(bytes32 indexed agentId, string name, address indexed owner);
    event AgentUpdated(bytes32 indexed agentId);
    event AgentDeactivated(bytes32 indexed agentId);

    modifier onlyAgentOwner(bytes32 agentId) {
        require(agents[agentId].owner == msg.sender, "Not agent owner");
        _;
    }

    function registerAgent(
        string calldata name,
        string calldata description,
        string calldata metadataURI,
        string calldata endpoint,
        bool x402Support
    ) external returns (bytes32 agentId) {
        agentId = keccak256(abi.encodePacked(name, msg.sender, block.timestamp));
        require(agents[agentId].owner == address(0), "Agent already exists");

        agents[agentId] = AgentCard({
            name: name,
            description: description,
            metadataURI: metadataURI,
            endpoint: endpoint,
            x402Support: x402Support,
            active: true,
            owner: msg.sender,
            registeredAt: block.timestamp
        });

        agentIds.push(agentId);
        emit AgentRegistered(agentId, name, msg.sender);
    }

    function updateMetadata(bytes32 agentId, string calldata metadataURI, string calldata endpoint)
        external onlyAgentOwner(agentId)
    {
        agents[agentId].metadataURI = metadataURI;
        agents[agentId].endpoint = endpoint;
        emit AgentUpdated(agentId);
    }

    function deactivateAgent(bytes32 agentId) external onlyAgentOwner(agentId) {
        agents[agentId].active = false;
        emit AgentDeactivated(agentId);
    }

    function getAgent(bytes32 agentId) external view returns (AgentCard memory) {
        return agents[agentId];
    }

    function getAgentCount() external view returns (uint256) {
        return agentIds.length;
    }

    // ──────────────── Reputation Registry ────────────────

    struct Feedback {
        address user;
        bytes32 agentId;
        uint8   score;      // 0-100
        string  tag;        // e.g. "starred"
        string  comment;
        uint256 timestamp;
    }

    mapping(bytes32 => Feedback[]) public agentFeedback;
    mapping(bytes32 => uint256) public agentTotalScore;
    mapping(bytes32 => uint256) public agentFeedbackCount;

    event FeedbackGiven(bytes32 indexed agentId, address indexed user, uint8 score, string tag);

    function giveFeedback(
        bytes32 agentId,
        uint8 score,
        string calldata tag,
        string calldata comment
    ) external {
        require(agents[agentId].owner != address(0), "Agent not found");
        require(score <= 100, "Score must be 0-100");

        agentFeedback[agentId].push(Feedback({
            user: msg.sender,
            agentId: agentId,
            score: score,
            tag: tag,
            comment: comment,
            timestamp: block.timestamp
        }));

        agentTotalScore[agentId] += score;
        agentFeedbackCount[agentId] += 1;

        emit FeedbackGiven(agentId, msg.sender, score, tag);
    }

    function getReputationScore(bytes32 agentId) external view returns (uint256 avgScore, uint256 totalFeedback) {
        totalFeedback = agentFeedbackCount[agentId];
        if (totalFeedback == 0) return (0, 0);
        avgScore = agentTotalScore[agentId] / totalFeedback;
    }

    function getFeedbackPage(bytes32 agentId, uint256 offset, uint256 limit)
        external view returns (Feedback[] memory page)
    {
        Feedback[] storage all = agentFeedback[agentId];
        uint256 end = offset + limit;
        if (end > all.length) end = all.length;
        if (offset >= all.length) return new Feedback[](0);
        page = new Feedback[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            page[i - offset] = all[i];
        }
    }
}
