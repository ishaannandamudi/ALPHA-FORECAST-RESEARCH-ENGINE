"""Independent target regression on exact admitted TRAIN event relations."""

from typing import TYPE_CHECKING

from afre.cross_sectional.normalization import average
from afre.event_conditioned.artifacts import EventConditionedModel, EventConditionedObservation
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.events import EventReference
from afre.event_conditioned.matching import base_context
from afre.event_conditioned.schema import EventModelFamily
from afre.multihorizon.alignment import completed_fit
from afre.schema import require
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from afre.statistical_models.linear_algebra import householder_qr
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.event_conditioned.repository import EventRepository


def feature_keys(spec: EventConditioningSpec) -> tuple[str, ...]:
    return tuple(r.key for r in spec.value_rules if r.use_as_feature) + tuple(
        "reaction:" + r.fingerprint for r in spec.reaction_specs
    )


def fit_for(
    repo: "EventRepository",
    spec: EventConditioningSpec,
    ids: tuple[str, ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> EventConditionedModel:
    require(
        0 < len(ids) <= repo.event_bounds.samples and len(set(ids)) == len(ids),
        "event TRAIN sample bound/duplicates",
    )
    base_context(repo, spec)
    baseline = repo.resolve(FittedModelArtifact, spec.base_model_id)
    completed_fit(repo, "m_fits", "artifact_id", baseline.fingerprint)
    repo._validate_links(baseline)
    inputs = repo.resolve(ModelFitInputs, baseline.fit_inputs_id)
    matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
    rows = {r.sample_id: r for r in matrix.rows}
    observations = tuple(repo.resolve(EventConditionedObservation, i) for i in sorted(ids))
    for o in observations:
        require(
            o.spec_id == spec.fingerprint
            and o.scope is PredictionScope.IN_SAMPLE
            and o.sample_id in rows,
            "event fit only exact admitted TRAIN",
        )
        repo._validate_links(o)
        row = rows[o.sample_id]
        require(
            o.target_id == row.target_id
            and o.origin == row.origin
            and row.data_available_ns <= inputs.training_cutoff_ns,
            "event TRAIN target cutoff",
        )
    admitted = tuple(o for o in observations if o.event_id is not None)
    samples = {o.sample_id for o in admitted}
    require(len(samples) >= spec.minimum_samples, "insufficient event TRAIN samples")
    require(
        len({o.event_id for o in admitted}) >= spec.minimum_events,
        "insufficient distinct TRAIN events",
    )
    require(
        started_ns >= max(inputs.training_cutoff_ns, baseline.available_ns),
        "event fit before baseline/cutoff",
    )
    classes: dict[str, list[EventConditionedObservation]] = {}
    for o in admitted:
        assert o.event_id is not None
        cls = repo.resolve(EventReference, o.event_id).event_class.value
        classes.setdefault(cls, []).append(o)
    class_values = tuple(
        (
            cls,
            average(tuple(rows[o.sample_id].response for o in peers)),
            len({o.sample_id for o in peers}),
        )
        for cls, peers in sorted(classes.items())
        if len({o.sample_id for o in peers}) >= spec.minimum_class_samples
    )
    keys = feature_keys(spec)
    coefficients: tuple[float, ...] = ()
    if spec.family is EventModelFamily.EVENT_CLASS_OFFSET:
        require(bool(class_values), "no event class meets minimum TRAIN count")
    else:
        require(len(keys) <= repo.event_bounds.reaction_features + 3, "event feature bound")
        x = tuple((1.0, *(dict(o.values)[key] for key in keys)) for o in admitted)
        y = tuple(rows[o.sample_id].response for o in admitted)
        coefficients = householder_qr(
            x, y, spec.qr_tolerance, spec.condition_limit
        ).coefficients
    return EventConditionedModel(
        spec.fingerprint,
        matrix.fingerprint,
        ids,
        tuple(o.fingerprint for o in observations if o.event_id is None),
        keys,
        coefficients,
        class_values,
        inputs.training_cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
        len(samples),
    )
