"""Operating-system differences kept in one place."""
import os
import subprocess
import sys

IS_WINDOWS = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'


def open_camera(index: int = 0):
    """Open a webcam with the capture backend that suits this OS."""
    import cv2
    if IS_WINDOWS:
        backend = cv2.CAP_DSHOW  # DirectShow opens faster than the default and skips a warning
    elif IS_MAC:
        backend = cv2.CAP_AVFOUNDATION
    else:
        backend = cv2.CAP_ANY
    return cv2.VideoCapture(index, backend)


def screenshots_folder() -> str:
    """The folder the OS itself saves screenshots to."""
    if IS_WINDOWS:
        # Ask Windows for its Screenshots known folder rather than guessing, because
        # Pictures is often moved (e.g. into OneDrive).
        import ctypes
        import uuid
        folder_id = uuid.UUID('{b7bede81-df94-4682-a7d8-57a52620b86f}')  # FOLDERID_Screenshots
        guid = (ctypes.c_byte * 16).from_buffer_copy(folder_id.bytes_le)
        path_ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(path_ptr)) == 0:
            path = path_ptr.value
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return path
        return os.path.join(os.path.expanduser('~'), 'Pictures', 'Screenshots')
    if IS_MAC:
        result = subprocess.run(['defaults', 'read', 'com.apple.screencapture', 'location'],
                                capture_output=True, text=True)
        location = os.path.expanduser(result.stdout.strip())
        if result.returncode == 0 and os.path.isdir(location):
            return location
        return os.path.expanduser('~/Desktop')
    return os.path.join(os.path.expanduser('~'), 'Pictures')
