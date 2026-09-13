"""Tests for Screen Capture Engine, Window Cropping, and DPI Awareness.

Verifies:
- DPI awareness initialization
- Full screen, active window, region capture abstractions
- Mock image injection for headless and automated CI environments
- Hermes window pattern detection and bounding box extraction
"""

from PIL import Image
import pytest

from app.capture.screen_grabber import ScreenGrabber, init_dpi_awareness


class TestDPIAwareness:
    """Tests DPI awareness initialization."""

    def test_init_dpi_awareness_returns_bool(self) -> None:
        result = init_dpi_awareness()
        assert isinstance(result, bool)


class TestScreenGrabberMockMode:
    """Tests ScreenGrabber behavior with injected mock images (headless verification)."""

    @pytest.fixture
    def mock_screen_image(self) -> Image.Image:
        img = Image.new("RGB", (1920, 1080), color="#123456")
        return img

    @pytest.fixture
    def grabber(self, mock_screen_image: Image.Image) -> ScreenGrabber:
        sg = ScreenGrabber()
        sg.set_test_mock_image(mock_screen_image)
        return sg

    def test_capture_full_screen_mock(self, grabber: ScreenGrabber) -> None:
        img = grabber.capture_full_screen()
        assert img is not None
        assert img.size == (1920, 1080)

    def test_capture_active_window_mock(self, grabber: ScreenGrabber) -> None:
        img, title = grabber.capture_active_window()
        assert img is not None
        assert img.size == (1920, 1080)
        assert "Mock" in title

    def test_capture_window_hwnd_mock(self, grabber: ScreenGrabber) -> None:
        img, title = grabber.capture_window_hwnd(12345)
        assert img is not None
        assert img.size == (1920, 1080)
        assert "Mock" in title

    def test_capture_region_mock(self, grabber: ScreenGrabber) -> None:
        bbox = (100, 100, 500, 400)
        img = grabber.capture_region(bbox)
        assert img is not None
        assert img.size == (400, 300)

    def test_capture_window_by_title_pattern_mock(self, grabber: ScreenGrabber) -> None:
        img, title = grabber.capture_window_by_title_pattern("Hermes")
        assert img is not None
        assert "Mock" in title

    def test_clear_mock_image(self, grabber: ScreenGrabber) -> None:
        grabber.set_test_mock_image(None)
        assert grabber._mock_image is None


class TestScreenGrabberLiveEnvironment:
    """Tests ScreenGrabber methods in live execution without mock injection."""

    def test_live_desktop_capture_returns_image_or_none(self) -> None:
        sg = ScreenGrabber()
        # In interactive Windows session, this returns real PIL Image
        img = sg.capture_full_screen(all_screens=False)
        if img is not None:
            assert isinstance(img, Image.Image)
            assert img.width > 0 and img.height > 0

    def test_get_window_bounds_invalid_hwnd(self) -> None:
        sg = ScreenGrabber()
        bounds = sg.get_window_bounds(0)
        assert bounds is None

    def test_capture_window_hwnd_zero_returns_empty(self) -> None:
        sg = ScreenGrabber()
        img, title = sg.capture_window_hwnd(0)
        assert img is None
        assert title == ""

    def test_find_hermes_windows_returns_list(self) -> None:
        sg = ScreenGrabber()
        windows = sg.find_hermes_windows()
        assert isinstance(windows, list)
        for hwnd, title in windows:
            assert isinstance(hwnd, int)
            assert isinstance(title, str)

    def test_capture_active_window_respects_min_dimensions(self) -> None:
        sg = ScreenGrabber()
        # Should gracefully return Desktop or None when min dimensions are impossible
        img, title = sg.capture_active_window(min_width=99999, min_height=99999)
        # In headless/non-interactive, falls back to Desktop
        assert title == "Desktop" or img is not None
