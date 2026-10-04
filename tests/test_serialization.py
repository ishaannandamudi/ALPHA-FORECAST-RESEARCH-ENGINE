import json
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

import pytest

from afre.lineage import Parameter
from afre.schema import Artifact, ContractError
from afre.serialization import _unwire, _wire, canonical_json, deserialize
from examples.foundation_demo import Demo


def test_round_trip_every_contract_family(demo: Demo) -> None:
    from tests.test_lifecycle import result

    artifacts = (
        demo.instrument,
        demo.origin,
        *demo.features,
        demo.row,
        demo.target,
        demo.experiment,
        result(demo),
    )
    for artifact in artifacts:
        payload = canonical_json(artifact)
        assert deserialize(payload) == artifact
        assert deserialize(payload).fingerprint == artifact.fingerprint
        assert canonical_json(deserialize(payload)) == payload


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "{}",
        "[]",
        "{",
        '{"schema_version":"2.0","artifact":null}',
        '{"schema_version":"1.0","artifact":null}',
        '{"schema_version":"1.0","artifact":NaN}',
        '{"schema_version":"1.0","artifact":Infinity}',
        '{"schema_version":"1.0","artifact":{"x":1,"x":2}}',
        '{"schema_version":"1.0","artifact":{"$type":"os.system","fields":{}}}',
        '{"schema_version":"1.0","artifact":{"$enum":"Untrusted","value":"x"}}',
        '{"schema_version":"1.0","artifact":{"$enum":"DataQuality","value":"invalid","extra":0}}',
        '{"schema_version":"1.0","artifact":{"$enum":"DataQuality","value":"unknown"}}',
        '{"schema_version":"1.0","artifact":{"$type":"InstrumentId","fields":[]}}',
        '{"schema_version":"1.0","artifact":{"$type":"InstrumentId","fields":{}}}',
    ],
)
def test_reject_unsafe_json(payload: str) -> None:
    with pytest.raises(ContractError):
        deserialize(payload)


def test_noncanonical_payloads_and_missing_extra_fields(demo: Demo) -> None:
    valid = canonical_json(demo.instrument)
    with pytest.raises(ContractError):
        deserialize(" " + valid)
    with pytest.raises(ContractError):
        deserialize(json.dumps(json.loads(valid)))
    parsed = json.loads(valid)
    parsed["artifact"]["fields"]["extra"] = "unknown"
    with pytest.raises(ContractError):
        deserialize(json.dumps(parsed, sort_keys=True, separators=(",", ":")))
    parsed = json.loads(valid)
    parsed["artifact"]["fields"]["value"] = {"untrusted": "mapping"}
    with pytest.raises(ContractError):
        deserialize(json.dumps(parsed, sort_keys=True, separators=(",", ":")))
    # An unsorted stored payload fails canonical replay.
    parsed = json.loads(canonical_json(demo.experiment.model))
    parsed["artifact"]["fields"]["feature_set"]["fields"]["definitions"].reverse()
    with pytest.raises(ContractError):
        deserialize(json.dumps(parsed, sort_keys=True, separators=(",", ":")))


def test_decoder_resource_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("afre.serialization.MAX_PAYLOAD_BYTES", 5)
    with pytest.raises(ContractError):
        deserialize("123456")
    with pytest.raises(ContractError):
        canonical_json(Parameter("x", 0))
    monkeypatch.setattr("afre.serialization.MAX_PAYLOAD_BYTES", 16 * 1024 * 1024)
    monkeypatch.setattr("afre.serialization.MAX_DEPTH", 1)
    with pytest.raises(ContractError):
        _wire((((1,),),))
    with pytest.raises(ContractError):
        _unwire([[[1]]])
    with pytest.raises(ContractError):
        deserialize("[" * 10000 + "]" * 10000)


def test_unregistered_and_tampered_values(demo: Demo) -> None:
    @dataclass(frozen=True, slots=True)
    class Unknown(Artifact):
        x: int

    with pytest.raises(ContractError):
        canonical_json(Unknown(1))

    class UnknownEnum(Enum):
        X = "x"

    with pytest.raises(ContractError):
        _wire(UnknownEnum.X)
    with pytest.raises(ContractError):
        _wire(float("nan"))
    for value in ([], {}, object()):
        with pytest.raises(ContractError):
            _wire(value)
    tampered = replace(demo.features[0])
    object.__setattr__(tampered, "available_ns", -1)
    with pytest.raises(ContractError):
        deserialize(canonical_json(tampered))
    payload = canonical_json(Parameter("x", 1))
    assert isinstance(_unwire([1, True, None, "x"]), tuple)
    assert deserialize(payload) == Parameter("x", 1)


def test_unsigned_zero_unicode_and_nonfinite() -> None:
    assert canonical_json(Parameter("unicode", "Δ")) == canonical_json(
        Parameter("unicode", "Δ")
    )
    assert canonical_json(Parameter("x", -0.0)) == canonical_json(Parameter("x", 0.0))
    for number in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ContractError):
            Parameter("x", number)
    with pytest.raises(ContractError):
        deserialize(cast_bad_payload())


def cast_bad_payload() -> Any:
    return 1


def test_invalid_unicode_fails_closed() -> None:
    with pytest.raises(ContractError, match="Unicode"):
        Parameter("unicode", "\ud800")
    with pytest.raises(ContractError):
        deserialize("\ud800")
