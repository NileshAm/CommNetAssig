from src.security import ASHRMessage, SecurityManager, tamper_auth_tag


def _security_manager():
    manager = SecurityManager(
        trusted_neighbors={"R1": {"R2"}, "R2": {"R1"}},
        shared_keys={"R1": b"key-r1", "R2": b"key-r2"},
    )
    return manager


def test_ashr_rejects_invalid_hmac():
    manager = _security_manager()
    message = ASHRMessage(
        message_type="ASHR_LSA",
        sender_router_id="R2",
        area_id=1,
        sequence_number=1,
        ttl=16,
        body={"links": [{"neighbor": "R1", "cost": 0.2}]},
    )
    manager.sign_message(message)
    tamper_auth_tag(message)

    result = manager.validate_message("R1", message)

    assert not result.accepted
    assert "HMAC" in result.reason


def test_ashr_rejects_replayed_sequence_number():
    manager = _security_manager()
    message = ASHRMessage(
        message_type="ASHR_LSA",
        sender_router_id="R2",
        area_id=1,
        sequence_number=7,
        ttl=16,
        body={"links": [{"neighbor": "R1", "cost": 0.2}]},
    )
    manager.sign_message(message)

    first = manager.validate_message("R1", message)
    replay = manager.validate_message("R1", message)

    assert first.accepted
    assert not replay.accepted
    assert "sequence" in replay.reason


def test_ashr_rejects_fake_low_cost_route_even_with_valid_hmac():
    manager = _security_manager()
    message = ASHRMessage(
        message_type="ASHR_LSA",
        sender_router_id="R2",
        area_id=1,
        sequence_number=8,
        ttl=16,
        body={"destination": "R10", "advertised_cost": 0},
    )
    manager.sign_message(message)

    result = manager.validate_message("R1", message)

    assert not result.accepted
    assert "low-cost" in result.reason
