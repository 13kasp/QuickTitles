"""
QuickTitles — AudioPlayer: plays WAV slices via pyaudio or subprocess fallback.
"""

import os
import platform
import subprocess
import tempfile
import threading
from typing import Optional

from utils import _dlog
from core.ffmpeg import _NO_WINDOW


class AudioPlayer:
    """
    Plays a slice of a WAV file by piping ffmpeg PCM into pyaudio.
    Falls back to ffplay/aplay/afplay if pyaudio is not installed.
    """

    _CHUNK     = 2048
    _RATE      = 44100
    _CHANNELS  = 2

    def __init__(self, wav_path: str):
        self._wav  = wav_path
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        try:
            import pyaudio as _pa
            self._pa = _pa
            self._use_pyaudio = True
        except ImportError:
            self._pa = None
            self._use_pyaudio = False

    def play(self, start: Optional[float], end: Optional[float], on_done=None):
        self._stop_evt.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            try: proc.kill(); proc.wait()
            except Exception: pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._worker, args=(start, end, on_done), daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_evt.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            try: proc.kill(); proc.wait()
            except Exception: pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _set_proc(self, proc):
        with self._lock:
            self._proc = proc

    def _ffmpeg_cmd(self, start, end) -> list:
        cmd = [os.environ.get("FFMPEG_BINARY", "ffmpeg"), "-y", "-loglevel", "quiet"]
        if start is not None:
            cmd += ["-ss", str(start)]
        cmd += ["-i", self._wav]
        if start is not None and end is not None:
            cmd += ["-t", str(max(0.01, end - start))]
        cmd += ["-f", "s16le", "-ar", str(self._RATE), "-ac", str(self._CHANNELS), "pipe:1"]
        return cmd

    def _worker(self, start, end, on_done):
        stopped = False
        try:
            if self._use_pyaudio:
                stopped = self._stream_pyaudio(start, end)
            else:
                stopped = self._stream_subprocess(start, end)
        except Exception as e:
            _dlog(f"[AudioPlayer] {e}")
            stopped = True
        finally:
            self._set_proc(None)
            if on_done and not stopped and not self._stop_evt.is_set():
                try:
                    on_done()
                except Exception:
                    pass

    def _stream_pyaudio(self, start, end) -> bool:
        import pyaudio

        proc = subprocess.Popen(
            self._ffmpeg_cmd(start, end),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
        self._set_proc(proc)

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=self._CHANNELS,
            rate=self._RATE,
            output=True,
            frames_per_buffer=self._CHUNK,
        )
        nbytes  = self._CHUNK * self._CHANNELS * 2
        stopped = False
        try:
            while True:
                if self._stop_evt.is_set():
                    stopped = True
                    break
                data = proc.stdout.read(nbytes)
                if not data:
                    break
                stream.write(data)
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            if proc.poll() is None:
                proc.kill(); proc.wait()

        return stopped

    def _stream_subprocess(self, start, end) -> bool:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            ex_cmd = ["ffmpeg", "-y", "-loglevel", "quiet"]
            if start is not None:
                ex_cmd += ["-ss", str(start)]
            ex_cmd += ["-i", self._wav]
            if start is not None and end is not None:
                ex_cmd += ["-t", str(max(0.01, end - start))]
            ex_cmd += [tmp.name]

            ex = subprocess.Popen(ex_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=_NO_WINDOW)
            self._set_proc(ex)
            ex.wait()
            if self._stop_evt.is_set():
                return True

            if os.name == "nt":
                play_cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp.name]
            elif platform.system() == "Darwin":
                play_cmd = ["afplay", tmp.name]
            else:
                play_cmd = ["aplay", "-q", tmp.name]

            proc = subprocess.Popen(play_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=_NO_WINDOW)
            self._set_proc(proc)
            if self._stop_evt.is_set():
                proc.kill(); proc.wait()
                return True
            proc.wait()
            return self._stop_evt.is_set()
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
