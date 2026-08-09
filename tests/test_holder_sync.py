"""Tests for incremental Solana Candy Machine transaction scanner."""

from __future__ import annotations

import json
from services import holder_rewards

def test_sync_genesis_mints_no_new_signatures(tmp_path, monkeypatch):
    # Тимчасовий файл для уникнення впливу на прод
    mints_file = tmp_path / "genesis_mints.json"
    mints_file.write_text(
        json.dumps({
            "collection": "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC",
            "candyMachine": "BpHBqJAVeSRuEjyeEyuTkjUL9ocarY63rHBzyEVwmGrM",
            "mints": ["mint-1", "mint-2"],
            "lastSignature": "old-sig-123"
        }),
        encoding="utf-8"
    )
    
    monkeypatch.setattr(holder_rewards, "MINTS_FILE", mints_file)
    monkeypatch.setattr(holder_rewards, "DATA_DIR", tmp_path)
    holder_rewards._mints_cache = None
    
    captured_payloads = []
    
    def fake_post(url, **kwargs):
        payload = kwargs.get("json", {})
        captured_payloads.append(payload)
        class Resp:
            def raise_for_status(self):
                pass
            def json(self):
                return {"result": []}
        return Resp()
        
    monkeypatch.setattr(holder_rewards.requests, "post", fake_post)
    
    res = holder_rewards.sync_genesis_mints(rpc_url="https://mock-rpc")
    
    assert res["success"] is True
    assert res["new_mints_count"] == 0
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["method"] == "getSignaturesForAddress"
    assert captured_payloads[0]["params"][1]["until"] == "old-sig-123"


def test_sync_genesis_mints_with_new_mints(tmp_path, monkeypatch):
    mints_file = tmp_path / "genesis_mints.json"
    mints_file.write_text(
        json.dumps({
            "collection": "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC",
            "candyMachine": "BpHBqJAVeSRuEjyeEyuTkjUL9ocarY63rHBzyEVwmGrM",
            "mints": ["mint-1"],
            "lastSignature": "old-sig"
        }),
        encoding="utf-8"
    )
    
    monkeypatch.setattr(holder_rewards, "MINTS_FILE", mints_file)
    monkeypatch.setattr(holder_rewards, "DATA_DIR", tmp_path)
    holder_rewards._mints_cache = None
    
    def fake_post(url, **kwargs):
        payload = kwargs.get("json", {})
        method = payload.get("method")
        
        class Resp:
            def raise_for_status(self):
                pass
            def json(self):
                if method == "getSignaturesForAddress":
                    return {
                        "result": [
                            {"signature": "new-sig-2", "err": None},
                            {"signature": "new-sig-1", "err": None}
                        ]
                    }
                elif method == "getTransaction":
                    sig = payload["params"][0]
                    if sig == "new-sig-1":
                        # Містить новий мінт NFT
                        return {
                            "result": {
                                "meta": {
                                    "postTokenBalances": [
                                        {
                                            "mint": "mint-new-1",
                                            "uiTokenAmount": {"decimals": 0, "amount": "1"}
                                        },
                                        {
                                            "mint": "6YRxC2pwqttw11zy4v2cGgV3DztpPX7zSHrFFcA4nmqC", # collection NFT
                                            "uiTokenAmount": {"decimals": 0, "amount": "1"}
                                        }
                                    ]
                                }
                            }
                        }
                    elif sig == "new-sig-2":
                        # Вже існуючий мінт або порожня транзакція
                        return {
                            "result": {
                                "meta": {
                                    "postTokenBalances": [
                                        {
                                            "mint": "mint-1",
                                            "uiTokenAmount": {"decimals": 0, "amount": "1"}
                                        }
                                    ]
                                }
                            }
                        }
                return {"result": None}
        return Resp()
        
    monkeypatch.setattr(holder_rewards.requests, "post", fake_post)
    
    res = holder_rewards.sync_genesis_mints(rpc_url="https://mock-rpc")
    
    assert res["success"] is True
    assert res["scanned_transactions"] == 2
    assert res["new_mints_count"] == 1
    assert res["total_mints_count"] == 2
    
    # Перевіряємо вміст оновленого файлу
    updated = json.loads(mints_file.read_text(encoding="utf-8"))
    assert updated["lastSignature"] == "new-sig-2"
    assert "mint-new-1" in updated["mints"]
    assert "mint-1" in updated["mints"]


def test_sync_does_not_write_into_sugar_data(tmp_path, monkeypatch):
    """genesis_mints.json має рівно одного письменника в кожному репо.

    Раніше Промт дзеркалив цей файл у <SUGAR_PROJECT_PATH>/data, а Sugar
    `snapshot-holders.mjs` писав назад сюди — той самий файл із двох репо.
    Саме цим шляхом тестові мінти одного разу опинились у бойових даних Sugar
    (фікс 340ef27). Цей тест ловить повернення дзеркала.
    """
    mints_file = tmp_path / "genesis_mints.json"
    mints_file.write_text(
        json.dumps({"mints": ["mint-1"], "lastSignature": "sig-1"}), encoding="utf-8"
    )
    monkeypatch.setattr(holder_rewards, "MINTS_FILE", mints_file)
    monkeypatch.setattr(holder_rewards, "DATA_DIR", tmp_path)
    holder_rewards._mints_cache = None

    # Існуюча тека — саме той випадок, коли старий код записав би дублікат.
    sugar_root = tmp_path / "sugar"
    (sugar_root / "data").mkdir(parents=True)
    monkeypatch.setenv("SUGAR_PROJECT_PATH", str(sugar_root))

    def fake_post(url, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"result": []}

        return Resp()

    monkeypatch.setattr(holder_rewards.requests, "post", fake_post)

    res = holder_rewards.sync_genesis_mints(rpc_url="https://mock-rpc")

    assert res["success"] is True
    assert not (sugar_root / "data" / "genesis_mints.json").exists(), (
        "Промт знову дзеркалить genesis_mints.json у Sugar — це повертає двох "
        "письменників одного файла"
    )
