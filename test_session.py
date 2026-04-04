#!/usr/bin/env python3
"""Session save/restore regression tests."""

import asyncio
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.registry import get_all_tools
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import UserMessage, AssistantMessage


class SessionTester:
    """Test session save/load functionality."""
    
    def __init__(self):
        self.store = Store(get_default_app_state())
        set_global_store(self.store)
        
        tools = get_all_tools()
        self.query_engine = QueryEngine(QueryEngineConfig(
            cwd=self.store.get_state().cwd,
            tools=tools,
            get_app_state=self.store.get_state,
            set_app_state=lambda f: self.store.set_state(f)
        ))
    
    def test_save_empty_session(self) -> bool:
        """Test 1: Save empty session."""
        print("\n" + "=" * 60)
        print("TEST 1: Save Empty Session")
        print("=" * 60)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            self.query_engine.save_session(temp_path)
            
            # Verify file exists and is valid JSON
            assert os.path.exists(temp_path), "Session file not created"
            
            with open(temp_path, 'r') as f:
                data = json.load(f)
            
            assert data.get("version") == 1, "Wrong version"
            assert "messages" in data, "No messages field"
            assert data["messages"] == [], "Empty session should have empty messages"
            assert "cwd" in data, "No cwd field"
            
            print(f"✅ PASS: Empty session saved to {temp_path}")
            print(f"   Messages: {len(data['messages'])}")
            print(f"   CWD: {data['cwd']}")
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            return False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_load_empty_session(self) -> bool:
        """Test 2: Load empty session."""
        print("\n" + "=" * 60)
        print("TEST 2: Load Empty Session")
        print("=" * 60)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # Save and reload
            self.query_engine.save_session(temp_path)
            
            # Create new engine and load
            tools = get_all_tools()
            new_engine = QueryEngine(QueryEngineConfig(
                cwd="/tmp",
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f)
            ))
            
            result = new_engine.load_session(temp_path)
            assert result, "Load failed"
            assert len(new_engine.messages) == 0, "Should have 0 messages"
            
            print(f"✅ PASS: Empty session loaded successfully")
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            return False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_save_load_with_messages(self) -> bool:
        """Test 3: Save and load session with messages."""
        print("\n" + "=" * 60)
        print("TEST 3: Save/Load Session With Messages")
        print("=" * 60)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # Add some messages
            from pilotcode.types.message import UserMessage, AssistantMessage
            
            user_msg = UserMessage(content="Hello")
            assistant_msg = AssistantMessage(content="Hi there!")
            
            self.query_engine.messages.append(user_msg)
            self.query_engine.messages.append(assistant_msg)
            
            # Save
            self.query_engine.save_session(temp_path)
            
            # Verify saved data
            with open(temp_path, 'r') as f:
                data = json.load(f)
            
            assert len(data["messages"]) == 2, f"Expected 2 messages, got {len(data['messages'])}"
            
            # Create new engine and load
            tools = get_all_tools()
            new_engine = QueryEngine(QueryEngineConfig(
                cwd="/tmp",
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f)
            ))
            
            result = new_engine.load_session(temp_path)
            assert result, "Load failed"
            assert len(new_engine.messages) == 2, f"Expected 2 messages after load, got {len(new_engine.messages)}"
            
            # Verify message content
            assert isinstance(new_engine.messages[0], UserMessage), "First message should be UserMessage"
            assert isinstance(new_engine.messages[1], AssistantMessage), "Second message should be AssistantMessage"
            assert new_engine.messages[0].content == "Hello", "User message content mismatch"
            assert new_engine.messages[1].content == "Hi there!", "Assistant message content mismatch"
            
            print(f"✅ PASS: Session with {len(new_engine.messages)} messages saved and loaded")
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_load_nonexistent_file(self) -> bool:
        """Test 4: Load non-existent file."""
        print("\n" + "=" * 60)
        print("TEST 4: Load Non-existent File")
        print("=" * 60)
        
        try:
            result = self.query_engine.load_session("/nonexistent/path/session.json")
            assert result == False, "Should return False for non-existent file"
            
            print(f"✅ PASS: Correctly returned False for non-existent file")
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            return False
    
    def test_cwd_persistence(self) -> bool:
        """Test 5: CWD persistence in session."""
        print("\n" + "=" * 60)
        print("TEST 5: CWD Persistence")
        print("=" * 60)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            # Set custom CWD
            original_cwd = self.query_engine.config.cwd
            self.query_engine.config.cwd = "/custom/working/dir"
            
            # Save
            self.query_engine.save_session(temp_path)
            
            # Create new engine with different CWD
            tools = get_all_tools()
            new_engine = QueryEngine(QueryEngineConfig(
                cwd="/different/cwd",
                tools=tools,
                get_app_state=self.store.get_state,
                set_app_state=lambda f: self.store.set_state(f)
            ))
            
            # Load and verify CWD restored
            new_engine.load_session(temp_path)
            assert new_engine.config.cwd == "/custom/working/dir", f"CWD not restored: {new_engine.config.cwd}"
            
            print(f"✅ PASS: CWD persisted and restored: {new_engine.config.cwd}")
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {e}")
            return False
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            # Restore original
            self.query_engine.config.cwd = original_cwd
    
    async def run_all(self):
        """Run all session tests."""
        print("\n" + "=" * 60)
        print("SESSION SAVE/LOAD REGRESSION TESTS")
        print("=" * 60)
        
        results = []
        
        results.append(("Save Empty Session", self.test_save_empty_session()))
        results.append(("Load Empty Session", self.test_load_empty_session()))
        results.append(("Save/Load With Messages", self.test_save_load_with_messages()))
        results.append(("Load Non-existent File", self.test_load_nonexistent_file()))
        results.append(("CWD Persistence", self.test_cwd_persistence()))
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, r in results if r)
        total = len(results)
        
        for name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status}: {name}")
        
        print(f"\nTotal: {passed}/{total} passed")
        
        if passed == total:
            print("\n🎉 All session tests passed!")
            return 0
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            return 1


async def main():
    """Main entry point."""
    tester = SessionTester()
    exit_code = await tester.run_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
