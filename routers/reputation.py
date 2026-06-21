from fastapi import APIRouter
import asyncio
from reputation import get_reputation_sync

router = APIRouter()


@router.get("/reputation")
async def get_reputation():
    """
    Returns current on-chain reputation of agentId 113
    from the official ERC-8004 ReputationRegistry on Mantle Mainnet.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_reputation_sync)
