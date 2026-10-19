"""Measure fresh-process startup to native main-window readiness and idle working set."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import psutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    samples = []
    for index in range(3):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        started = time.perf_counter()
        process = subprocess.Popen([str(args.exe.resolve()), '--quit-after', '10000'],
                                   cwd=args.exe.resolve().parent, startupinfo=startup)
        parent = psutil.Process(process.pid)
        window = []
        while not window and time.perf_counter() - started < 120:
            if process.poll() is not None:
                raise RuntimeError(f'App exited before GUI ready: {process.returncode}')
            pids = {process.pid} | {p.pid for p in parent.children(recursive=True)}

            @callback_type
            def enum(hwnd, _param, owned=pids, found=window):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in owned:
                    title = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd, title, len(title))
                    if title.value == 'Tải Hồ Sơ Thuế':
                        found.append(hwnd)
                return True

            user32.EnumWindows(enum, 0)
            time.sleep(0.02)
        if not window:
            raise RuntimeError('GUI startup timeout; app left for inspection')
        ready = time.perf_counter() - started
        time.sleep(1)
        children = [parent] + parent.children(recursive=True)
        rss = sum(p.memory_info().rss for p in children if p.is_running())
        for hwnd in window:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # safe close of idle main window
        process.wait(timeout=60)
        if process.returncode != 0:
            raise RuntimeError(f'GUI exited with {process.returncode}')
        samples.append({'startup_s': ready, 'idle_working_set_bytes': rss})
        print(json.dumps({'run': index + 1, **samples[-1]}), flush=True)
    report = {'method': '3 fresh-process launches; stopwatch to native main window; working set parent+child after 1s idle; OS caches not flushed',
              'windows': psutil.WINDOWS, 'logical_cpus': os.cpu_count(), 'ram_bytes': psutil.virtual_memory().total,
              'exe_bytes': args.exe.stat().st_size, 'samples': samples,
              'median_startup_s': statistics.median(x['startup_s'] for x in samples),
              'median_idle_working_set_bytes': statistics.median(x['idle_working_set_bytes'] for x in samples)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
