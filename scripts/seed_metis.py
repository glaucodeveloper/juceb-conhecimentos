#!/usr/bin/env python3
"""Create isolated Metis tensors for the prepared JUCEB research-map units."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECIALITY = json.loads((ROOT / "speciality.json").read_text(encoding="utf-8"))
SLUG = SPECIALITY["slug"]


def read_env() -> dict[str, str]:
    path = Path.home() / ".config/cognoscere/cognoscere.env"
    result: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    result.update({key: value for key, value in os.environ.items() if key.startswith("COGNOSCERE_")})
    return result


def request(url: str, token: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Metis HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Resposta JSON inválida do Metis")
    return result


def write_manifest(path: Path, manifest: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    settings = read_env()
    host = settings.get("COGNOSCERE_HOST", "127.0.0.1")
    port = settings.get("COGNOSCERE_PORT", "19194")
    token = settings.get("COGNOSCERE_API_TOKEN", "")
    api = f"http://{host}:{port}"
    if not token:
        raise SystemExit("COGNOSCERE_API_TOKEN ausente em ~/.config/cognoscere/cognoscere.env")

    health = request(api + "/health", token)
    if not health.get("ok") or not health.get("model_loaded"):
        raise SystemExit("Metis não está ativo com o modelo carregado")
    service_root = Path(health.get("specialities_root", "")).expanduser().resolve()
    installed_path = (service_root / SLUG).resolve()
    if installed_path != ROOT.resolve():
        raise SystemExit(f"Execute na pasta instalada em {installed_path}; esta pasta é {ROOT.resolve()}")

    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = manifest.get("candidate_units", [])
    if not candidates:
        raise SystemExit("Nenhuma unidade candidata no manifest.json")
    memory_root = ROOT / "memories"
    active_tensor = memory_root / "active.safetensors"
    previous_skills = {row.get("id"): row for row in manifest.get("skills", [])}
    seeding = manifest.get("status") == "metis-seeding-in-progress"
    if active_tensor.exists() and not seeding:
        raise SystemExit("Já existe uma memória ativa; o script só retoma uma geração marcada como em andamento")

    skills = []
    for candidate in candidates:
        old = previous_skills.get(candidate["id"], {})
        tensor = ROOT / candidate["tensor_path"]
        ready = (
            old.get("status") == "ready"
            and old.get("source_sha256") == candidate["source_sha256"]
            and tensor.is_file()
        )
        entry = {key: candidate[key] for key in (
            "id", "code", "title", "topic_key", "kind", "source_okf", "tensor_path", "source_sha256"
        )}
        entry["status"] = "ready" if ready else "pending"
        if ready:
            entry["tensor_sha256"] = hashlib.sha256(tensor.read_bytes()).hexdigest()
        skills.append(entry)
    manifest["skills"] = skills
    manifest["status"] = "metis-seeding-in-progress"
    write_manifest(manifest_path, manifest)

    previous_speciality = health.get("active_speciality")
    previous_unit = health.get("active_unit_id")
    try:
        request(api + "/specialities/create", token, {
            "slug": SLUG,
            "title": SPECIALITY["title"],
            "description": SPECIALITY["description"],
        })
        request(api + "/specialities/load", token, {"slug": SLUG})
        if not active_tensor.is_file():
            request(api + "/specialities/commit", token, {
                "slug": SLUG,
                "kind": "speciality_seed",
                "title": "JUCEB speciality initialization",
                "source": "Cognoscere Metis local service",
                "artifact": {"status": "empty_unit_seed", "slug": SLUG},
            })
        if not active_tensor.is_file():
            raise SystemExit("Metis não criou memories/active.safetensors")

        seed_bytes = active_tensor.read_bytes()
        seed_hash = hashlib.sha256(seed_bytes).hexdigest()
        for index, candidate in enumerate(candidates, start=1):
            entry = next(row for row in manifest["skills"] if row["id"] == candidate["id"])
            tensor = ROOT / candidate["tensor_path"]
            if entry["status"] == "ready":
                print(f"[{index}/{len(candidates)}] {candidate['id']} já estava pronto")
                continue
            tensor.parent.mkdir(parents=True, exist_ok=True)
            tensor.write_bytes(seed_bytes)
            okf_path = "source-okfs/" + candidate["source_okf"]
            artifact = json.loads((ROOT / okf_path).read_text(encoding="utf-8"))
            request(api + "/specialities/unit/commit", token, {
                "slug": SLUG,
                "unit_id": candidate["id"],
                "okf_path": okf_path,
                "artifact": artifact,
            })
            entry["tensor_sha256"] = hashlib.sha256(tensor.read_bytes()).hexdigest()
            entry["status"] = "ready"
            write_manifest(manifest_path, manifest)
            print(f"[{index}/{len(candidates)}] {candidate['id']} pronto")

        manifest["status"] = "units-ready-monitor-pending"
        write_manifest(manifest_path, manifest)
        metadata_path = ROOT / "speciality.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        metadata.setdefault("metadata", {}).update({
            "status": "units-ready-monitor-pending",
            "metis_units_ready": True,
            "metis_tensors_ready": False,
        })
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(candidates)} unidades da speciality {SLUG} prontas; tensor do monitor ainda pendente; seed_sha256={seed_hash}")
    finally:
        if previous_speciality and (previous_speciality != SLUG or previous_unit):
            restore_path = "/specialities/unit/load" if previous_unit else "/specialities/load"
            restore_body = {"slug": previous_speciality}
            if previous_unit:
                restore_body["unit_id"] = previous_unit
            try:
                request(api + restore_path, token, restore_body)
            except Exception as exc:
                print(f"Aviso: não foi possível restaurar a especialidade ativa anterior: {exc}")


if __name__ == "__main__":
    main()
