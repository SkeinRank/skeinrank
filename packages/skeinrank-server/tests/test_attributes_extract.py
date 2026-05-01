def test_attributes_extract_contract_default_profile(client):
    payload = {
        "text": "k8s timeout on prod",
    }
    r = client.post("/v1/attributes/extract", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "request_id" in data
    assert data["profile"] == "default_it"
    assert isinstance(data["attributes"], list) and len(data["attributes"]) == 1
    assert data["attributes"][0]["slot"] == "TOOL"
    assert data["attributes"][0]["value"] == "kubernetes"
    assert data["passport"] is None


def test_attributes_extract_debug_omits_inactive_model_stages(client):
    payload = {
        "text": "k8s timeout on prod",
        "profile": "default_it",
        "debug": True,
    }
    r = client.post("/v1/attributes/extract", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["passport"] is not None
    assert data["passport"]["profile_id"] == "default_it"
    assert "stage_status" not in data["passport"]


def test_attributes_extract_contract_debug_and_stage_overrides(client):
    payload = {
        "text": "Kubernetes timeout on api-server",
        "profile": "default_it",
        "debug": True,
        "use_gliner": True,
        "use_e5": False,
        "use_keybert": True,
    }
    r = client.post("/v1/attributes/extract", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["profile"] == "default_it"
    assert data["passport"] is not None
    assert data["passport"]["profile_id"] == "default_it"
    stages = {item["stage"]: item for item in data["passport"]["stage_status"]}
    assert stages["gliner"]["enabled"] is True
    assert "e5" not in stages
    assert stages["keybert"]["enabled"] is True
