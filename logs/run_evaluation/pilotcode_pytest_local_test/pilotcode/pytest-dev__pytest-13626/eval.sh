#!/bin/bash
set -uxo pipefail
source /opt/miniconda3/bin/activate
conda activate testbed
cd /testbed
git config --global --add safe.directory /testbed
cd /testbed
git status
git show
git -c core.fileMode=false diff 5898e9c7a1b8aee15c4c834298ba7ed32ce92cb9
source /opt/miniconda3/bin/activate
conda activate testbed
python -m pip install -e .
git checkout 5898e9c7a1b8aee15c4c834298ba7ed32ce92cb9 src/_pytest/runner.py testing/test_runner.py
git apply -v - <<'EOF_114329324912'
diff --git a/src/_pytest/runner.py b/src/_pytest/runner.py
index 18d3591abfe..d9209befd48 100644
--- a/src/_pytest/runner.py
+++ b/src/_pytest/runner.py
@@ -128,23 +128,25 @@ def runtestprotocol(
         # This only happens if the item is re-run, as is done by
         # pytest-rerunfailures.
         item._initrequest()  # type: ignore[attr-defined]
-    rep = call_and_report(item, "setup", log)
-    reports = [rep]
-    if rep.passed:
-        if item.config.getoption("setupshow", False):
-            show_test_item(item)
-        if not item.config.getoption("setuponly", False):
-            reports.append(call_and_report(item, "call", log))
-    # If the session is about to fail or stop, teardown everything - this is
-    # necessary to correctly report fixture teardown errors (see #11706)
-    if item.session.shouldfail or item.session.shouldstop:
-        nextitem = None
-    reports.append(call_and_report(item, "teardown", log, nextitem=nextitem))
-    # After all teardown hooks have been called
-    # want funcargs and request info to go away.
-    if hasrequest:
-        item._request = False  # type: ignore[attr-defined]
-        item.funcargs = None  # type: ignore[attr-defined]
+    try:
+        rep = call_and_report(item, "setup", log)
+        reports = [rep]
+        if rep.passed:
+            if item.config.getoption("setupshow", False):
+                show_test_item(item)
+            if not item.config.getoption("setuponly", False):
+                reports.append(call_and_report(item, "call", log))
+        # If the session is about to fail or stop, teardown everything - this is
+        # necessary to correctly report fixture teardown errors (see #11706)
+        if item.session.shouldfail or item.session.shouldstop:
+            nextitem = None
+        reports.append(call_and_report(item, "teardown", log, nextitem=nextitem))
+    finally:
+        # After all teardown hooks have been called (or an exception was reraised)
+        # want funcargs and request info to go away.
+        if hasrequest:
+            item._request = False  # type: ignore[attr-defined]
+            item.funcargs = None  # type: ignore[attr-defined]
     return reports
 
 
diff --git a/testing/test_runner.py b/testing/test_runner.py
index 3cb3c3a3841..3cf6be69de9 100644
--- a/testing/test_runner.py
+++ b/testing/test_runner.py
@@ -7,6 +7,7 @@
 from pathlib import Path
 import sys
 import types
+from typing import cast
 
 from _pytest import outcomes
 from _pytest import reports
@@ -494,6 +495,37 @@ def test_func():
         else:
             assert False, "did not raise"
 
+    def test_keyboardinterrupt_clears_request_and_funcargs(
+        self, pytester: Pytester
+    ) -> None:
+        """Ensure that an item's fixtures are cleared quickly even if exiting
+        early due to a keyboard interrupt (#13626)."""
+        item = pytester.getitem(
+            """
+            import pytest
+
+            @pytest.fixture
+            def resource():
+                return object()
+
+            def test_func(resource):
+                raise KeyboardInterrupt("fake")
+        """
+        )
+        assert isinstance(item, pytest.Function)
+        assert item._request
+        assert item.funcargs == {}
+
+        try:
+            runner.runtestprotocol(item, log=False)
+        except KeyboardInterrupt:
+            pass
+        else:
+            assert False, "did not raise"
+
+        assert not cast(object, item._request)
+        assert not item.funcargs
+
 
 class TestSessionReports:
     def test_collect_result(self, pytester: Pytester) -> None:

EOF_114329324912
: '>>>>> Start Test Output'
pytest -rA src/_pytest/runner.py testing/test_runner.py
: '>>>>> End Test Output'
git checkout 5898e9c7a1b8aee15c4c834298ba7ed32ce92cb9 src/_pytest/runner.py testing/test_runner.py
