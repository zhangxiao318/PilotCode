#!/usr/bin/env python3
"""Test issues: duplicate output and incomplete analysis."""

import asyncio
import websockets
import json
import sys
import os
import subprocess
import time

# Kill existing processes
os.system('powershell -Command "Get-NetTCPConnection -LocalPort 8090,8091 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"')
time.sleep(2)

# Start server
print("=== Starting Server ===")
server_proc = subprocess.Popen(
    [sys.executable, '-u', '-c', '''
import sys
sys.path.insert(0, 'src')
from pilotcode.web.server import run_server_standalone
run_server_standalone('127.0.0.1', 8090, '.')
'''],
    stdout=sys.stdout,
    stderr=sys.stdout,
    text=True,
    cwd=os.path.dirname(__file__),
    bufsize=1
)

time.sleep(5)

async def test_query(query_text, test_name):
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Query: {query_text}")
    print('='*60)
    
    try:
        ws = await websockets.connect('ws://127.0.0.1:8091', ping_interval=None)
        
        await ws.send(json.dumps({
            'type': 'query',
            'message': query_text,
            'message_id': 1
        }))
        
        chunks = []
        for i in range(100):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                msg_type = data.get('type')
                
                if msg_type == 'streaming_chunk':
                    chunk = data.get('chunk', '')
                    chunks.append(chunk)
                    print(f'[Chunk {len(chunks)}] {repr(chunk[:80])}...')
                elif msg_type == 'tool_call':
                    print(f"[Tool] {data.get('tool_name')}: {data.get('tool_input', {})}")
                elif msg_type == 'tool_result':
                    result = data.get('result', '')[:60]
                    print(f"[Result] {result}...")
                elif msg_type == 'permission_request':
                    req_id = data.get('request_id')
                    print(f'[Permission] {req_id}')
                    await ws.send(json.dumps({
                        'type': 'permission_response',
                        'request_id': req_id,
                        'granted': True,
                        'for_session': True
                    }))
                elif msg_type == 'streaming_end':
                    print('[Stream End]')
                    break
            except asyncio.TimeoutError:
                print('[Timeout]')
                break
        
        await ws.close()
        
        # Check for duplicates
        full_response = ''.join(chunks)
        print(f"\n[Full Response Length: {len(full_response)}]")
        print(f"[Response Preview: {repr(full_response[:200])}...]")
        
        # Check for obvious duplicates
        if full_response:
            lines = full_response.split('\n')
            unique_lines = list(dict.fromkeys(lines))
            if len(lines) != len(unique_lines):
                print(f"[WARNING] Found {len(lines) - len(unique_lines)} duplicate lines")
        
        return full_response
        
    except Exception as e:
        print(f'[Error] {e}')
        return ""

async def main():
    # Test 1: "几点了"
    await test_query("几点了", "Time Query")
    
    await asyncio.sleep(3)
    
    # Test 2: "分析当前目录程序功能"
    await test_query("分析当前目录程序功能", "Analysis Query")

try:
    asyncio.run(main())
finally:
    print('\n=== Stopping Server ===')
    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except:
        server_proc.kill()
    print('Done')
