from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..errors import ConfigurationError
from ..types import JSONInput, JSONValue, SplitSubset
from .base import BaseResource, dataset_path


class SplitsResource(BaseResource):
    def get(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("getSplitState", path_params=dataset_path(project_id, dataset_id))

    def reset(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("resetSplit", path_params=dataset_path(project_id, dataset_id))

    def validate(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("validateSplit", path_params=dataset_path(project_id, dataset_id))

    def manifest(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("getSplitManifest", path_params=dataset_path(project_id, dataset_id))

    def plan(
        self,
        project_id: str,
        dataset_id: str,
        *,
        train_bps: int,
        validation_bps: int,
        test_bps: int,
        seed: int | None = None,
        stratify_by_labels: bool | None = None,
    ) -> JSONValue:
        ratios = (train_bps, validation_bps, test_bps)
        if any(value < 0 or value > 10_000 for value in ratios) or sum(ratios) != 10_000:
            raise ConfigurationError("split ratios must be basis points between 0 and 10000 that sum to 10000")
        body: dict[str, JSONInput] = {
            "ratios": {
                "trainBps": train_bps,
                "validationBps": validation_bps,
                "testBps": test_bps,
            }
        }
        if seed is not None:
            body["seed"] = seed
        if stratify_by_labels is not None:
            body["stratifyByLabels"] = stratify_by_labels
        return self._client.call(
            "planSplit",
            path_params=dataset_path(project_id, dataset_id),
            json_body=body,
        )

    def apply(self, project_id: str, dataset_id: str, plan: Mapping[str, JSONInput]) -> JSONValue:
        return self._client.call(
            "applySplit",
            path_params=dataset_path(project_id, dataset_id),
            json_body={"plan": dict(plan)},
        )

    def assign(
        self,
        project_id: str,
        dataset_id: str,
        media_ids: Sequence[str],
        subset: SplitSubset,
        *,
        locked: bool = False,
        dry_run: bool = False,
    ) -> JSONValue:
        return self._client.call(
            "assignSplitMedia",
            path_params=dataset_path(project_id, dataset_id),
            query={"dryRun": dry_run},
            json_body={"mediaIds": list(media_ids), "subset": subset, "locked": locked},
        )

    def set_locked(
        self,
        project_id: str,
        dataset_id: str,
        media_ids: Sequence[str],
        locked: bool,
    ) -> JSONValue:
        return self._client.call(
            "setSplitLocked",
            path_params=dataset_path(project_id, dataset_id),
            json_body={"mediaIds": list(media_ids), "locked": locked},
        )

    def rebalance(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("rebalanceSplit", path_params=dataset_path(project_id, dataset_id))
