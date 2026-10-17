"""macOS native system-audio capture through ScreenCaptureKit (macOS 13+), via PyObjC.

ScreenCaptureKit captures the audio of every application (independent of the output
device and the volume slider). It requires the "Screen & System Audio Recording"
permission for the app that launched EVE (Terminal when using run.command).

Verified on macOS 27.0 / Apple M2: real samples from another process are delivered as
48 kHz float32 non-interleaved stereo.

Notes learned during verification:
* ``excludesCurrentProcessAudio`` is left False: macOS attributes child processes to the
  same "responsible" app, so excluding our process silenced *all* audio launched from the
  same terminal. EVE itself never plays audio, so nothing is lost.
* Every PyObjC completion handler must return None and must never raise, otherwise the
  process aborts with an uncaught NSException.
"""

from __future__ import annotations

import logging
import platform
import sys
import threading
import weakref
from typing import Any

import numpy as np

from eve.audio.capture_interface import AudioCaptureBackend, AudioSource, SourceKind
from eve.audio.capture_status import CaptureStatus

log = logging.getLogger(__name__)

SOURCE_ID = "sck:system"
SC_STREAM_OUTPUT_SCREEN = 0
SC_STREAM_OUTPUT_AUDIO = 1
SC_ERROR_USER_DECLINED = -3801
K_AUDIO_FORMAT_FLAG_IS_FLOAT = 0x1
K_AUDIO_FORMAT_FLAG_NON_INTERLEAVED = 0x20
PRIVACY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"

PERMISSION_HELP = (
    "macOS needs permission to capture system audio. Open System Settings → Privacy & Security → "
    "Screen & System Audio Recording, allow the app that started EVE (Terminal when you used "
    "run.command), then quit and reopen that app and press Retry."
)

_objc_ready = False
_StreamOutput: Any = None


def _macos_version() -> tuple[int, ...]:
    release = platform.mac_ver()[0]
    try:
        return tuple(int(p) for p in release.split(".") if p.isdigit())
    except ValueError:
        return ()


def _ensure_objc_classes() -> None:
    """Define the Objective-C delegate class once (ObjC class names are process-global)."""
    global _objc_ready, _StreamOutput
    if _objc_ready:
        return
    import objc
    from Foundation import NSObject

    protocols = [objc.protocolNamed("SCStreamOutput"), objc.protocolNamed("SCStreamDelegate")]

    class EVEStreamOutput(NSObject, protocols=protocols):  # type: ignore[call-arg]
        def initWithOwner_(self, owner):
            self = objc.super(EVEStreamOutput, self).init()
            if self is None:
                return None
            self._owner = weakref.ref(owner)
            return self

        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
            if output_type != SC_STREAM_OUTPUT_AUDIO:
                return
            owner = self._owner()
            if owner is not None:
                owner._on_sample_buffer(sample_buffer)

        def stream_didStopWithError_(self, stream, error):
            owner = self._owner()
            if owner is not None:
                owner._on_stream_stopped(error)

    _StreamOutput = EVEStreamOutput
    _objc_ready = True


def screen_capture_preflight() -> bool | None:
    """Whether the permission is already granted (never prompts). None if unknown."""
    try:
        import Quartz

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


class ScreenCaptureKitBackend(AudioCaptureBackend):
    key = "sck"
    display_name = "macOS system audio (ScreenCaptureKit)"

    def __init__(self, on_samples, on_status) -> None:
        super().__init__(on_samples, on_status)
        self._lock = threading.Lock()
        self._generation = 0
        self._stream: Any = None
        self._output: Any = None
        self._format: tuple[float, int, int, int] | None = None  # (rate, channels, flags, bits)
        self._callback_errors = 0
        self._requested_access = False

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "ScreenCaptureKit is only available on macOS"
        version = _macos_version()
        if version and version < (13,):
            return False, f"ScreenCaptureKit audio capture needs macOS 13 or newer (this is {platform.mac_ver()[0]})"
        try:
            import CoreMedia  # noqa: F401
            import ScreenCaptureKit  # noqa: F401
        except Exception as exc:
            return False, f"PyObjC ScreenCaptureKit bindings unavailable: {exc}"
        return True, ""

    def get_supported_sources(self) -> list[AudioSource]:
        return [
            AudioSource(
                SOURCE_ID,
                "System audio (all apps)",
                SourceKind.SYSTEM_OUTPUT,
                True,
                "Everything your Mac plays, captured with ScreenCaptureKit",
            )
        ]

    # -- start ---------------------------------------------------------------------------
    def start_capture(self, source_id: str | None = None) -> None:
        with self._lock:
            if self._stream is not None:
                return
            self._generation += 1
            generation = self._generation
        _ensure_objc_classes()
        import ScreenCaptureKit as SCK

        self._set_status(
            CaptureStatus.WAITING_FOR_PERMISSION, "Checking Screen & System Audio Recording permission…", "System audio"
        )

        def on_content(content, error):
            try:
                self._content_ready(generation, content, error)
            except Exception as exc:  # must never raise into Objective-C
                log.exception("ScreenCaptureKit setup failed")
                self._set_status(CaptureStatus.ERROR, f"Could not start ScreenCaptureKit: {exc}")

        SCK.SCShareableContent.getShareableContentWithCompletionHandler_(on_content)

    def _content_ready(self, generation: int, content: Any, error: Any) -> None:
        if generation != self._generation:
            return  # stopped while waiting
        if error is not None:
            code = int(error.code())
            if code == SC_ERROR_USER_DECLINED:
                self._request_access_once()
                self._set_status(CaptureStatus.PERMISSION_DENIED, PERMISSION_HELP)
            else:
                self._set_status(CaptureStatus.ERROR, f"ScreenCaptureKit error {code}: {error.localizedDescription()}")
            return
        import CoreMedia as CM
        import ScreenCaptureKit as SCK

        displays = content.displays() if content is not None else None
        if not displays:
            self._set_status(
                CaptureStatus.DEVICE_UNAVAILABLE, "ScreenCaptureKit reported no displays to attach the audio stream to."
            )
            return
        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(displays[0], [])
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setSampleRate_(48000)
        config.setChannelCount_(2)
        config.setExcludesCurrentProcessAudio_(False)
        # The stream must include video; keep it as cheap as possible (2x2 px, 1 fps).
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(CM.CMTimeMake(1, 1))
        config.setQueueDepth_(3)

        output = _StreamOutput.alloc().initWithOwner_(self)
        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(content_filter, config, output)
        ok, err = stream.addStreamOutput_type_sampleHandlerQueue_error_(output, SC_STREAM_OUTPUT_AUDIO, None, None)
        if not ok:
            self._set_status(CaptureStatus.ERROR, f"Could not attach the audio output: {err}")
            return
        # A screen output avoids "stream output NOT found" log spam; frames are ignored.
        stream.addStreamOutput_type_sampleHandlerQueue_error_(output, SC_STREAM_OUTPUT_SCREEN, None, None)
        with self._lock:
            if generation != self._generation:
                return
            self._stream = stream
            self._output = output
            self._format = None
        self._set_status(CaptureStatus.CONNECTING, "Starting system audio stream…", "System audio")

        def on_started(start_error):
            try:
                if generation != self._generation:
                    return
                if start_error is not None:
                    code = int(start_error.code())
                    with self._lock:
                        self._stream = None
                        self._output = None
                    if code == SC_ERROR_USER_DECLINED:
                        self._request_access_once()
                        self._set_status(CaptureStatus.PERMISSION_DENIED, PERMISSION_HELP)
                    else:
                        self._set_status(
                            CaptureStatus.ERROR,
                            f"System audio stream failed to start ({code}): {start_error.localizedDescription()}",
                        )
            except Exception:
                log.exception("start handler failed")

        stream.startCaptureWithCompletionHandler_(on_started)

    def _request_access_once(self) -> None:
        """Ask macOS to list this app in the privacy pane (shows the system prompt once)."""
        if self._requested_access:
            return
        self._requested_access = True
        try:
            import Quartz

            Quartz.CGRequestScreenCaptureAccess()
        except Exception:
            log.debug("CGRequestScreenCaptureAccess unavailable", exc_info=True)

    # -- callbacks (ScreenCaptureKit dispatch queue) ---------------------------------------
    def _on_sample_buffer(self, sample_buffer: Any) -> None:
        try:
            import CoreMedia as CM

            fmt = self._format
            if fmt is None:
                description = CM.CMSampleBufferGetFormatDescription(sample_buffer)
                asbd = CM.CMAudioFormatDescriptionGetStreamBasicDescription(description)
                # (mSampleRate, mFormatID, mFormatFlags, mBytesPerPacket, mFramesPerPacket,
                #  mBytesPerFrame, mChannelsPerFrame, mBitsPerChannel, mReserved)
                fmt = (float(asbd[0]), int(asbd[6]), int(asbd[2]), int(asbd[7]))
                self._format = fmt
                log.info("ScreenCaptureKit audio format: %.0f Hz, %d ch, flags=0x%x, %d bit", *fmt)
                self._set_status(CaptureStatus.RECEIVING_AUDIO, "", "System audio")
            rate, channels, flags, bits = fmt
            block = CM.CMSampleBufferGetDataBuffer(sample_buffer)
            if block is None:
                return
            length = CM.CMBlockBufferGetDataLength(block)
            if length <= 0:
                return
            status, data = CM.CMBlockBufferCopyDataBytes(block, 0, length, None)
            if status != 0 or data is None:
                return
            if flags & K_AUDIO_FORMAT_FLAG_IS_FLOAT and bits == 32:
                samples = np.frombuffer(data, dtype=np.float32)
            elif bits == 16:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                return
            channels = max(1, channels)
            frames = samples.shape[0] // channels
            if frames == 0:
                return
            samples = samples[: frames * channels]
            if channels == 1:
                mono = samples
            elif flags & K_AUDIO_FORMAT_FLAG_NON_INTERLEAVED:
                mono = samples.reshape(channels, frames).mean(axis=0, dtype=np.float32)
            else:
                mono = samples.reshape(frames, channels).mean(axis=1, dtype=np.float32)
            self._emit_samples(mono, int(rate))
        except Exception:
            self._callback_errors += 1
            if self._callback_errors <= 3:
                log.exception("failed to convert a ScreenCaptureKit audio buffer")

    def _on_stream_stopped(self, error: Any) -> None:
        try:
            with self._lock:
                self._stream = None
                self._output = None
            description = error.localizedDescription() if error is not None else "unknown reason"
            code = int(error.code()) if error is not None else 0
            if code == SC_ERROR_USER_DECLINED:
                self._set_status(CaptureStatus.PERMISSION_DENIED, PERMISSION_HELP)
            else:
                self._set_status(CaptureStatus.ERROR, f"System audio stream stopped: {description}")
        except Exception:
            log.exception("stop delegate failed")

    # -- stop ------------------------------------------------------------------------------
    def stop_capture(self) -> None:
        with self._lock:
            self._generation += 1
            stream = self._stream
            self._stream = None
            self._output = None
        if stream is not None:
            done = threading.Event()

            def on_stopped(error):
                done.set()

            try:
                stream.stopCaptureWithCompletionHandler_(on_stopped)
                if not done.wait(2.0):
                    log.warning("ScreenCaptureKit did not confirm stop within 2s")
            except Exception:
                log.exception("error while stopping ScreenCaptureKit stream")
        self._set_status(CaptureStatus.STOPPED)
