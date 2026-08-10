from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage


def _series_option(series, name, default):
    try:
        value = series.getOption(name)
    except Exception:
        value = None
    return default if value is None else value


def channel_axis_from_shape(shape):
    shape = tuple(int(s) for s in shape)
    if len(shape) < 3:
        return None
    if len(shape) == 3:
        if shape[-1] in (3, 4) and shape[0] > 8 and shape[1] > 8:
            return 2
        if shape[-1] <= 8 and shape[0] > 8 and shape[1] > 8:
            return 2
        if shape[0] <= 8 and shape[1] > 8 and shape[2] > 8:
            return 0
        return 0 if shape[0] <= 16 else None
    if len(shape) == 4:
        if shape[1] <= 8 and shape[2] > 16 and shape[3] > 16:
            return 1
        if shape[0] <= 8 and shape[2] > 16 and shape[3] > 16:
            return 0
        if shape[-1] <= 8 and shape[-2] > 16 and shape[-3] > 16:
            return 3
    candidates = [i for i, s in enumerate(shape) if s <= 16]
    for i in candidates:
        non_channel = [j for j in range(len(shape)) if j != i and shape[j] > 16]
        if len(non_channel) >= 2:
            return i
    return None


def spatial_axes_from_shape(shape):
    shape = tuple(int(s) for s in shape)
    if len(shape) == 2:
        return 0, 1
    c_axis = channel_axis_from_shape(shape)
    axes = [i for i in range(len(shape)) if i != c_axis]
    if len(shape) == 3:
        if c_axis == 0:
            return 1, 2
        if c_axis == 2:
            return 0, 1
    large_axes = [i for i in axes if shape[i] > 16]
    if len(large_axes) >= 2:
        return large_axes[-2], large_axes[-1]
    return axes[-2], axes[-1]


def spatial_shape_from_array(obj):
    shape = obj.shape if hasattr(obj, "shape") else np.asarray(obj).shape
    y_axis, x_axis = spatial_axes_from_shape(shape)
    return int(shape[y_axis]), int(shape[x_axis])


def channel_count_from_array(obj):
    shape = obj.shape if hasattr(obj, "shape") else np.asarray(obj).shape
    c_axis = channel_axis_from_shape(shape)
    return 1 if c_axis is None else int(shape[c_axis])


def crop_array_spatial(data, xmin, xmax, ymin, ymax):
    shape = tuple(int(s) for s in data.shape)
    y_axis, x_axis = spatial_axes_from_shape(shape)
    c_axis = channel_axis_from_shape(shape)
    slices = []
    for axis in range(len(shape)):
        if axis == y_axis:
            slices.append(slice(max(0, int(ymin)), min(shape[axis], int(ymax))))
        elif axis == x_axis:
            slices.append(slice(max(0, int(xmin)), min(shape[axis], int(xmax))))
        elif axis == c_axis:
            slices.append(slice(None))
        else:
            slices.append(0)
    return np.asarray(data[tuple(slices)])


def split_channels(arr):
    arr = np.asarray(arr)
    while arr.ndim > 2 and 1 in arr.shape:
        arr = np.squeeze(arr, axis=next(i for i, s in enumerate(arr.shape) if s == 1))
    if arr.ndim == 2:
        return [arr]
    c_axis = channel_axis_from_shape(arr.shape)
    if c_axis is None:
        return [arr[0] if arr.ndim > 2 else arr]
    y_axis, x_axis = spatial_axes_from_shape(arr.shape)
    moved = np.moveaxis(arr, [c_axis, y_axis, x_axis], [0, 1, 2])
    if moved.ndim > 3:
        moved = moved[(slice(None), slice(None), slice(None)) + (0,) * (moved.ndim - 3)]
    return [np.asarray(moved[i]) for i in range(moved.shape[0])]


def _to_uint8(ch):
    x = np.asarray(ch, dtype=np.float32)
    finite = np.isfinite(x)
    if not finite.any():
        return np.zeros(x.shape, dtype=np.uint8)
    vals = x[finite]
    lo, hi = np.percentile(vals, [1, 99])
    if hi <= lo:
        lo = float(vals.min())
        hi = float(vals.max())
    y = (x - lo) / (hi - lo + 1e-8)
    y = np.clip(y, 0.0, 1.0)
    return (y * 255).astype(np.uint8)


def _parse_channel_list(value, n_channels, fallback=None):
    if isinstance(value, str):
        raw = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = []
    out = []
    for item in raw:
        try:
            idx = int(item)
        except Exception:
            continue
        if 0 <= idx < n_channels and idx not in out:
            out.append(idx)
    if not out and fallback is not None:
        out = list(fallback)
    return out


def _array_to_qimage(arr):
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        qimg = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_Grayscale8)
    else:
        qimg = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_RGB888)
    return qimg.copy()


def compose_display_array(arr, series=None):
    channels = split_channels(arr)
    if len(channels) == 1:
        return _to_uint8(channels[0])
    mode = _series_option(series, "image_channel_mode", "auto") if series is not None else "auto"
    single = int(_series_option(series, "image_channel_single", 0)) if series is not None else 0
    overlay = _series_option(series, "image_channel_overlay", "0,1,2") if series is not None else "0,1,2"
    alpha = float(_series_option(series, "image_channel_alpha", 1.0)) if series is not None else 1.0
    alpha = float(np.clip(alpha, 0.0, 1.0))
    if mode == "none":
        return np.zeros(channels[0].shape, dtype=np.uint8)
    if mode == "auto" and np.asarray(arr).ndim == 3 and np.asarray(arr).shape[-1] in (3, 4):
        rgb = np.asarray(arr)[..., :3]
        if rgb.dtype != np.uint8:
            rgb = np.stack([_to_uint8(rgb[..., i]) for i in range(3)], axis=-1)
        return rgb.astype(np.uint8)
    if mode != "overlay":
        single = max(0, min(single, len(channels) - 1))
        return _to_uint8(channels[single])
    color_table = np.array([
        [255, 0, 0],
        [0, 255, 0],
        [0, 0, 255],
        [255, 0, 255],
        [0, 255, 255],
        [255, 255, 0],
        [255, 255, 255],
        [255, 128, 0],
    ], dtype=np.float32)
    rgb = np.zeros((*channels[0].shape, 3), dtype=np.float32)
    selected = _parse_channel_list(overlay, len(channels), fallback=[])
    if not selected:
        return np.zeros((*channels[0].shape, 3), dtype=np.uint8)
    for idx in selected:
        ch = _to_uint8(channels[idx]).astype(np.float32) / 255.0
        color = color_table[idx % len(color_table)]
        rgb = np.maximum(rgb, ch[..., None] * color[None, None, :] * alpha)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def compose_display_qimage(arr, series=None):
    return _array_to_qimage(compose_display_array(arr, series))


def read_image_array(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff", ".ome.tif", ".ome.tiff"} or ".ome." in path.name.lower():
        import tifffile
        return np.asarray(tifffile.imread(str(path)))
    try:
        import tifffile
        return np.asarray(tifffile.imread(str(path)))
    except Exception:
        import cv2
        arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise FileNotFoundError(f"Could not read image: {path}")
        if arr.ndim == 3 and arr.shape[-1] >= 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        return arr


def read_section_array(section):
    if section.series.src_dir.endswith("zarr"):
        import zarr
        return np.asarray(zarr.open(section.src_fp, mode="r")[:])
    return read_image_array(section.src_fp)


def read_section_channels(section):
    return split_channels(read_section_array(section))


def get_section_channel_count(section):
    try:
        return len(read_section_channels(section))
    except Exception:
        return 1


def get_section_display_qimage(section, series=None):
    arr = read_section_array(section)
    return compose_display_qimage(arr, series), channel_count_from_array(arr), spatial_shape_from_array(arr)
