from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import PathLike
from typing import Any, Literal, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
JSONInput: TypeAlias = JSONValue | Mapping[str, Any] | Sequence[Any]
Pathish: TypeAlias = str | PathLike[str]
QueryScalar: TypeAlias = str | int | float | bool
QueryValue: TypeAlias = QueryScalar | Mapping[str, Any] | Sequence[QueryScalar] | None
Query: TypeAlias = Mapping[str, QueryValue]

CreatableProjectDomain: TypeAlias = Literal[
    "Detection",
    "Instance segmentation",
    "Keypoint detection",
    "Classification",
]
AnnotationStatus: TypeAlias = Literal["none", "annotated", "partially_annotated", "to_revisit"]
DatasetFormat: TypeAlias = Literal[
    "coco",
    "yolo",
    "voc",
    "datumaro",
    "supervisely-video",
    "mot",
    "kitti",
    "mots",
    "zip",
]
MediaScope: TypeAlias = Literal["all", "annotated", "unannotated"]
MediaTypeSelection: TypeAlias = Literal["all", "images", "videos"]
SplitSubset: TypeAlias = Literal["train", "validation", "test", "unassigned"]
QualityScanMode: TypeAlias = Literal["quick", "deep"]
ActivityEventType: TypeAlias = Literal[
    "project.created",
    "project.renamed",
    "dataset.created",
    "dataset.renamed",
    "dataset.copied",
    "dataset.deleted",
    "media.imported",
    "media.deleted",
    "media.restored",
    "media.edited",
    "annotations.changed",
    "auto_annotation.accepted",
    "auto_annotation.rejected",
    "label.created",
    "label.renamed",
    "label.updated",
    "label.deleted",
    "version.created",
    "version.restored",
    "version.deleted",
    "split.applied",
    "project.typeChanged",
]
