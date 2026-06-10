#!/usr/bin/env python3
"""
Minimal test script for 3D robot visualization.
Run this on the Pi to check if create_3d_robot works correctly.

Usage:
    python3 test_3d_viz.py

This will:
1. Test imports
2. Test create_3d_robot with default angles
3. Save the figure to an HTML file for inspection
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("3D Robot Visualization Test")
print("=" * 60)

# Test 1: Check imports
print("\n[Test 1] Checking imports...")

try:
    import numpy as np
    print(f"  numpy: OK (version {np.__version__})")
except ImportError as e:
    print(f"  numpy: FAILED - {e}")
    sys.exit(1)

try:
    import plotly
    print(f"  plotly: OK (version {plotly.__version__})")
except ImportError as e:
    print(f"  plotly: FAILED - {e}")
    print("\n  FIX: Install plotly with: pip3 install plotly")
    sys.exit(1)

try:
    import plotly.graph_objects as go
    print(f"  plotly.graph_objects: OK")
except ImportError as e:
    print(f"  plotly.graph_objects: FAILED - {e}")
    sys.exit(1)

# Test 2: Import create_3d_robot
print("\n[Test 2] Importing create_3d_robot...")

try:
    from components.robot_3d import create_3d_robot
    print("  create_3d_robot: OK")
except ImportError as e:
    print(f"  create_3d_robot: FAILED - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Create figure with default angles
print("\n[Test 3] Creating 3D robot figure...")

try:
    # Test with neutral position (all servos at 90 degrees)
    test_angles = {i: 90 for i in range(12)}

    fig = create_3d_robot(
        servo_angles=test_angles,
        body_pitch=0,
        body_roll=0,
        body_yaw=0,
        height=450
    )
    print("  Figure created: OK")
    print(f"  Number of traces: {len(fig.data)}")

    # Check if figure has content
    if len(fig.data) == 0:
        print("  WARNING: Figure has no traces!")
    else:
        # List trace types
        trace_types = set(type(t).__name__ for t in fig.data)
        print(f"  Trace types: {trace_types}")

except Exception as e:
    print(f"  Figure creation: FAILED - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Save figure to HTML
print("\n[Test 4] Saving figure to HTML...")

output_file = "/tmp/robot_3d_test.html"
try:
    fig.write_html(output_file)
    print(f"  Saved to: {output_file}")
    print(f"  File size: {os.path.getsize(output_file)} bytes")
except Exception as e:
    print(f"  Save failed: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Test with string keys (as returned by JSON API)
print("\n[Test 5] Testing with string keys (JSON format)...")

try:
    # JSON API returns string keys
    json_angles = {"0": 90, "1": 85, "2": 95, "3": 90, "4": 85, "5": 95,
                   "6": 90, "7": 85, "8": 95, "9": 90, "10": 85, "11": 95}

    fig2 = create_3d_robot(
        servo_angles=json_angles,
        body_pitch=5,
        body_roll=-3,
        body_yaw=0,
        height=450
    )
    print(f"  Figure with string keys: OK")
    print(f"  Number of traces: {len(fig2.data)}")
except Exception as e:
    print(f"  String keys test: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Test 6: Test with empty angles (edge case)
print("\n[Test 6] Testing with empty angles (edge case)...")

try:
    fig3 = create_3d_robot(
        servo_angles={},
        body_pitch=0,
        body_roll=0,
        body_yaw=0,
        height=450
    )
    print(f"  Empty angles figure: OK")
    print(f"  Number of traces: {len(fig3.data)}")
except Exception as e:
    print(f"  Empty angles test: FAILED - {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
print("\nIf all tests passed, the visualization should work.")
print(f"Open {output_file} in a browser to verify the visualization.")
