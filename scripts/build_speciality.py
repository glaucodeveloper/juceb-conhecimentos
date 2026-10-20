#!/usr/bin/env python3
"""Convert the supplied OKF bundle into the Cognoscere Memory Studio layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "imports" / "OKF_Legislacao_Empresarial_BR_Bahia_2026-10-19.zip"
PREFIX = "okf-legislacao-empresarial/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "item"


def adapt(document: dict, schema: str, kind: str, topic_key: str) -> dict:
    result = dict(document)
    result["legacy_schema"] = document.get("schema")
    result["schema"] = schema
    result["kind"] = kind
    result["topic_key"] = topic_key
    result["provenance"] = {
        **(document.get("provenance") if isinstance(document.get("provenance"), dict) else {}),
        "conversion": "build_speciality.py",
        "converted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_archive": ARCHIVE.name,
    }
    return result


def read_json(zf: ZipFile, name: str) -> dict:
    try:
        value = json.loads(zf.read(name))
    except (KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"JSON inválido no ZIP: {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Esperado objeto JSON no ZIP: {name}")
    return value


def source_items(zf: ZipFile, root: str) -> list[str]:
    return sorted(
        name for name in zf.namelist()
        if name.startswith(root) and name.endswith(".okf")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    archive = args.archive.resolve()
    if not archive.is_file():
        raise SystemExit(f"ZIP de origem não encontrado: {archive}")

    existing_manifest_path = ROOT / "manifest.json"
    if existing_manifest_path.is_file():
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        has_live_pairs = bool(existing_manifest.get("skills")) or any(
            (ROOT / "memories").rglob("*.safetensors")
        ) if (ROOT / "memories").exists() else bool(existing_manifest.get("skills"))
        if has_live_pairs or existing_manifest.get("status") in {
            "metis-seeding-in-progress", "units-ready-monitor-pending", "units-ready", "active",
        }:
            raise SystemExit(
                "Já há pares/tensores Metis. A conversão foi interrompida para preservar as memórias; "
                "revise a atualização manualmente antes de reimportar."
            )

    with ZipFile(archive) as zf:
        unsafe = [
            name for name in zf.namelist()
            if name.startswith("/") or ".." in PurePosixPath(name).parts
        ]
        if unsafe:
            raise SystemExit(f"Caminhos inseguros no ZIP: {unsafe[:3]}")
        bad = zf.testzip()
        if bad:
            raise SystemExit(f"CRC inválido no ZIP: {bad}")

        curated_catalog = ROOT / "catalogo_fontes.json"
        if curated_catalog.is_file():
            registry = json.loads(curated_catalog.read_text(encoding="utf-8"))["acts"]
        else:
            registry = read_json(zf, PREFIX + "catalogo_fontes.json")["acts"]
        registry_by_id = {row["id"]: row for row in registry}
        reference_map: dict[str, dict] = {}
        reference_count = 0
        for member in source_items(zf, PREFIX + "okf/"):
            document = read_json(zf, member)
            source_id = document.get("id")
            if source_id not in registry_by_id:
                raise SystemExit(f"OKF sem registro correspondente no catálogo: {member} ({source_id})")
            rel = member.removeprefix(PREFIX + "okf/")
            output = ROOT / "source-okfs" / "references" / Path(rel)
            act = registry_by_id[source_id]
            converted = adapt(
                document,
                "okfforge.juceb.legal_source.v1",
                "legal_source_reference",
                "references/" + slug(source_id),
            )
            converted["catalog_status"] = "url-consulted" if act.get("source_verified") else "url-unverified"
            converted["official_source"] = {
                "id": source_id,
                "authority": act.get("authority"),
                "url": act.get("official_url"),
                "evidence_url": act.get("evidence_url", ""),
                "source_verified": bool(act.get("source_verified")),
                "notes": act.get("notes", ""),
            }
            write_json(output, converted)
            reference_map[source_id] = {
                "id": source_id,
                "title": act.get("title", document.get("title", source_id)),
                "authority": act.get("authority", ""),
                "url": act.get("official_url", ""),
                "evidence_url": act.get("evidence_url", ""),
                "reference_okf": output.relative_to(ROOT / "source-okfs").as_posix(),
                "source_verified": bool(act.get("source_verified")),
            }
            reference_count += 1

        concepts: list[dict] = []
        for member in source_items(zf, PREFIX + "okf_conceitos/"):
            document = read_json(zf, member)
            rel = member.removeprefix(PREFIX + "okf_conceitos/")
            output = ROOT / "source-okfs" / "concepts" / Path(rel)
            topic = str(PurePosixPath(rel).with_suffix(""))
            converted = adapt(
                document,
                "okfforge.juceb.research_map.v1",
                "legal_research_map",
                topic,
            )
            linked = []
            for relation in document.get("relations", []):
                if relation.get("type") != "fundamentado_em":
                    continue
                source = reference_map.get(relation.get("target"))
                if source:
                    linked.append(source)
            converted["linked_sources"] = linked
            converted["review_status"] = "unreviewed_legal_research_map"
            write_json(output, converted)
            unit_id = "juceb-" + slug(topic.replace("/", "-"))
            concepts.append({
                "id": unit_id,
                "code": unit_id.upper(),
                "title": document.get("title", unit_id),
                "topic_key": topic,
                "kind": "legal_research_map",
                "source_okf": output.relative_to(ROOT / "source-okfs").as_posix(),
                "tensor_path": f"memories/imported/skills/{unit_id}.safetensors",
                "source_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "status": "pending_metis_tensor",
            })

        compiled_count = 0
        compiled_root = ROOT / "okf_compilados"
        if compiled_root.exists():
            for input_path in sorted(compiled_root.rglob("*.okf")):
                document = json.loads(input_path.read_text(encoding="utf-8"))
                domain = input_path.relative_to(compiled_root)
                output = ROOT / "source-okfs" / "compiled" / domain
                converted = adapt(
                    document,
                    "okfforge.juceb.compiled_source.v1",
                    "automatically_extracted_legal_source",
                    "compiled/" + slug(str(document.get("id", input_path.stem))),
                )
                converted["review_status"] = "automatic_extraction_not_legally_consolidated"
                write_json(output, converted)
                compiled_count += 1

    current_time = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    write_json(ROOT / "sources" / "catalogo_fontes.json", {"acts": registry})
    write_json(ROOT / "source-okfs" / "index.json", {
        "schema": "cognoscere.juceb.source-index.v1",
        "generated_at": current_time,
        "archive": ARCHIVE.name,
        "archive_sha256": sha256(archive),
        "references": reference_count,
        "concept_maps": len(concepts),
        "compiled_source_candidates": compiled_count,
        "official_source_status": "incomplete",
        "legal_review": "pending",
    })

    metadata_path = ROOT / "speciality.json"
    speciality = json.loads(metadata_path.read_text(encoding="utf-8"))
    speciality["updated_at"] = current_time
    speciality["metadata"].update({"source_archive_sha256": sha256(archive)})
    write_json(metadata_path, speciality)

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest.update({
        "source_zip": archive.relative_to(ROOT).as_posix(),
        "source_zip_sha256": sha256(archive),
        "status": "awaiting-metis-tensor-generation",
        "skills": [],
        "candidate_units": concepts,
        "source_counts": {
            "catalog_references": reference_count,
            "concept_maps": len(concepts),
            "compiled_sources": compiled_count,
        },
    })
    manifest["monitor"]["source_sha256"] = sha256(ROOT / "okf" / "monitor.okf")
    write_json(ROOT / "manifest.json", manifest)

    monitor = json.loads((ROOT / "okf" / "monitor.okf").read_text(encoding="utf-8"))
    monitor["source"] = {"archive": archive.name, "sha256": sha256(archive)}
    monitor["skills"] = [
        {
            **{k: row[k] for k in (
                "id", "code", "title", "topic_key", "kind", "source_okf",
                "tensor_path", "source_sha256", "status",
            )},
            "purpose": "Mapear a questão e localizar fontes oficiais para revisão humana.",
        }
        for row in concepts
    ]
    write_json(ROOT / "okf" / "monitor.okf", monitor)
    print(json.dumps({
        "archive_sha256": sha256(archive),
        "references": reference_count,
        "concept_maps": len(concepts),
        "compiled_sources": compiled_count,
        "metis_tensors": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
