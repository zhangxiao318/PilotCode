#!/usr/bin/env python3
"""Test API connection and response."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pilotcode.utils.model_client import get_model_client, Message

async def test_api():
    """Test API connection."""
    print("Testing API connection...")
    print("=" * 50)
    
    client = get_model_client()
    
    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="Write a simple Python function to calculate factorial.")
    ]
    
    print(f"Base URL: {client.base_url}")
    print(f"Model: {client.model}")
    print()
    print("Sending request...")
    print("-" * 50)
    
    try:
        chunk_count = 0
        content_received = ""
        
        async for chunk in client.chat_completion(messages, stream=True):
            chunk_count += 1
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            
            if chunk_count <= 5:  # Print first 5 chunks
                print(f"Chunk {chunk_count}: {delta}")
            elif chunk_count == 6:
                print("... (more chunks)")
            
            if delta.get("content"):
                content_received += delta["content"]
        
        print("-" * 50)
        print(f"Total chunks: {chunk_count}")
        print(f"Content length: {len(content_received)}")
        print()
        print("Full response:")
        print(content_received[:500] + "..." if len(content_received) > 500 else content_received)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
