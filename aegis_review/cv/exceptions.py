"""Readable CV-domain errors for media, model, and pipeline failures."""

from __future__ import annotations


class CvPipelineError(RuntimeError):
    """Base class for CV analysis failures."""


class MediaDecodeError(CvPipelineError):
    """Raised when an image or video cannot be decoded."""


class ModelMissingError(CvPipelineError):
    """Raised when the expected weight file is absent."""


class InferenceError(CvPipelineError):
    """Raised when detector inference fails unexpectedly."""


class DatasetValidationError(CvPipelineError):
    """Raised when the YOLO dataset fails structural checks."""
