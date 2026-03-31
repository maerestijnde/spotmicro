#!/usr/bin/env python3
"""
Data Logger for MicroSpot
Records servo angles and IMU data to CSV files for post-session analysis.
"""
import csv
import io
import os
import time
import threading
from datetime import datetime
from pathlib import Path


class DataLogger:
    """
    Background data logger that samples servo angles and IMU readings
    at a configurable rate and writes buffered CSV to disk.
    """

    def __init__(self, log_dir: str = None):
        self._log_dir = Path(log_dir) if log_dir else Path(__file__).parent / "logs"
        self._log_dir.mkdir(exist_ok=True)

        self._recording = False
        self._thread = None
        self._stop_event = threading.Event()

        # Data sources (set by caller)
        self._get_servo_angles = None
        self._get_imu_angles = None

        # Current recording
        self._filename = None
        self._file = None
        self._writer = None
        self._buffer = io.StringIO()
        self._buffer_writer = None
        self._start_time = 0.0
        self._sample_count = 0
        self._last_flush = 0.0

        # Event queue
        self._pending_event = None

    def configure(self, get_servo_angles, get_imu_angles):
        """
        Set data source callbacks.

        Args:
            get_servo_angles: callable returning dict {channel: angle} (should be lock-free copy)
            get_imu_angles: callable returning (pitch, roll) tuple (should use cached values)
        """
        self._get_servo_angles = get_servo_angles
        self._get_imu_angles = get_imu_angles

    def start(self, sample_rate: float = 10.0):
        """
        Start recording data at given sample rate (Hz).

        Args:
            sample_rate: Samples per second (default 10Hz)
        """
        if self._recording:
            return False

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._filename = f"recording_{ts}.csv"
        filepath = self._log_dir / self._filename

        self._file = open(filepath, "w", newline="")
        self._writer = csv.writer(self._file)

        # Write header
        header = ["timestamp", "elapsed_ms"]
        header += [f"ch{i}" for i in range(12)]
        header += ["pitch", "roll", "event"]
        self._writer.writerow(header)

        self._start_time = time.time()
        self._sample_count = 0
        self._last_flush = self._start_time
        self._recording = True
        self._stop_event.clear()

        interval = 1.0 / sample_rate
        self._thread = threading.Thread(
            target=self._sample_loop, args=(interval,), daemon=True
        )
        self._thread.start()
        print(f"Recording started: {self._filename} @ {sample_rate}Hz")
        return True

    def stop(self):
        """Stop recording and flush remaining data."""
        if not self._recording:
            return None

        self._recording = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None

        filename = self._filename
        self._filename = None
        print(f"Recording stopped: {filename} ({self._sample_count} samples)")
        return filename

    def log_event(self, tag: str):
        """Tag the next sample with an event string (e.g. 'gait_start', 'pose_stand')."""
        self._pending_event = tag

    def is_recording(self) -> bool:
        return self._recording

    def current_filename(self) -> str | None:
        return self._filename

    def list_recordings(self) -> list:
        """List all CSV recordings with file info."""
        recordings = []
        for f in sorted(self._log_dir.glob("recording_*.csv"), reverse=True):
            stat = f.stat()
            recordings.append({
                "filename": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return recordings

    def get_filepath(self, filename: str) -> Path | None:
        """Get full path for a recording file (safe - prevents directory traversal)."""
        safe_name = Path(filename).name
        filepath = self._log_dir / safe_name
        if filepath.exists() and filepath.suffix == ".csv":
            return filepath
        return None

    def _sample_loop(self, interval: float):
        """Background sampling loop."""
        while not self._stop_event.is_set():
            try:
                self._write_sample()
            except Exception as e:
                print(f"DataLogger sample error: {e}")

            self._stop_event.wait(interval)

    def _write_sample(self):
        """Write one sample row to the CSV file."""
        if not self._writer or not self._file:
            return

        now = time.time()
        elapsed_ms = int((now - self._start_time) * 1000)

        # Get servo angles (lock-free dict copy)
        angles = {}
        if self._get_servo_angles:
            angles = self._get_servo_angles()

        # Get IMU (cached, no I2C)
        pitch, roll = 0.0, 0.0
        if self._get_imu_angles:
            try:
                pitch, roll = self._get_imu_angles()
            except Exception:
                pass

        # Build row
        row = [f"{now:.3f}", str(elapsed_ms)]
        row += [str(angles.get(i, angles.get(str(i), 90))) for i in range(12)]
        row += [f"{pitch:.2f}", f"{roll:.2f}"]

        # Event tag
        event = self._pending_event or ""
        self._pending_event = None
        row.append(event)

        self._writer.writerow(row)
        self._sample_count += 1

        # Flush every 1 second to minimize SD card writes
        if now - self._last_flush >= 1.0:
            self._file.flush()
            self._last_flush = now
