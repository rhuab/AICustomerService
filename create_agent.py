"""
One-time script to create the HR handbook Letta agent.
Print the agent ID and set LETTA_AGENT_ID in your .env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.letta_agent import create_hr_agent

if __name__ == "__main__":
    agent = create_hr_agent()
    print("Agent created. Add to .env file:")
    print(f"LETTA_AGENT_ID={agent.id}")
