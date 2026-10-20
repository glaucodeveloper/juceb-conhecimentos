"""Automatic article-level OKF partitioning and evidence retrieval for legal specialities."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


ARTICLE_RE = re.compile(r"\bArt\.?\s*(\d+[A-Z]?(?:-[A-Z])?)", re.IGNORECASE)
SUBDEVICE_RE = re.compile(
    r"(?m)^[ \t]*(?P<marker>§[ \t]*(?:\d+(?:º|°|o)?(?:-[A-Z])?|único)|"
    r"Parágrafo único\.?|[IVXLCDM]{1,8}[ \t]*[-–—]|[a-z][ \t]*\))(?=[ \t]|$)",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "essa", "esse", "esta", "este", "for", "na", "nas",
    "no", "nos", "o", "os", "ou", "para", "pela", "pelas", "pelo", "pelos",
    "por", "que", "se", "sem", "ser", "sua", "suas", "tambem", "um", "uma",
    "art", "artigo", "lei", "decreto", "norma", "sobre",
}


def _json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", normalized).strip("-._").lower() or "source"


def _article_marker(element: dict[str, Any]) -> str:
    name = str(element.get("name") or element.get("id") or "")
    match = ARTICLE_RE.search(name)
    if match:
        return f"Art. {match.group(1)}"
    return name.strip() or str(element.get("id") or "Dispositivo sem marcador")


def _group_article_fragments(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent page-boundary fragments for the same article; preserve all other candidates."""
    groups: list[dict[str, Any]] = []
    for ordinal, element in enumerate(elements, start=1):
        marker = _article_marker(element)
        content = str(element.get("content") or "").strip()
        if groups and groups[-1]["marker"].casefold() == marker.casefold():
            groups[-1]["fragments"].append({"ordinal": ordinal, "element": element, "content": content})
            if content and content not in groups[-1]["texts"]:
                groups[-1]["texts"].append(content)
            continue
        groups.append({
            "marker": marker,
            "fragments": [{"ordinal": ordinal, "element": element, "content": content}],
            "texts": [content] if content else [],
        })
    for group in groups:
        group["text"] = "\n\n".join(group.pop("texts"))
    return groups


def _split_subdevices(text: str, article_id: str) -> list[dict[str, Any]]:
    matches = list(SUBDEVICE_RE.finditer(text))
    result: list[dict[str, Any]] = []
    paragraph_id: str | None = None
    inciso_id: str | None = None
    counters = {"paragrafo": 0, "inciso": 0, "alinea": 0}
    for position, match in enumerate(matches):
        marker = " ".join(match.group("marker").split()).strip()
        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        content = text[match.start():end].strip()
        if marker.casefold().startswith("§") or marker.casefold().startswith("parágrafo"):
            kind = "paragrafo"
            counters[kind] += 1
            device_id = f"{article_id}-PAR-{counters[kind]}"
            paragraph_id, inciso_id = device_id, None
            parent_id = article_id
        elif re.match(r"^[a-z]\s*\)", marker, re.IGNORECASE):
            kind = "alinea"
            counters[kind] += 1
            device_id = f"{article_id}-AL-{counters[kind]}"
            parent_id = inciso_id or paragraph_id or article_id
        else:
            kind = "inciso"
            counters[kind] += 1
            device_id = f"{article_id}-INC-{counters[kind]}"
            inciso_id = device_id
            parent_id = paragraph_id or article_id
        result.append({
            "id": device_id,
            "type": f"{kind}_candidato",
            "marker": marker,
            "parent_id": parent_id,
            "content": content,
        })
    return result


def _document_source(document: dict[str, Any]) -> dict[str, Any]:
    sources = document.get("sources")
    source = sources[0] if isinstance(sources, list) and sources and isinstance(sources[0], dict) else {}
    return {
        "authority": source.get("authority", ""),
        "url": source.get("url", ""),
        "original_url": source.get("original_url", source.get("url", "")),
        "retrieved_at": source.get("retrieved_at", ""),
        "source_sha256": source.get("sha256", ""),
        "source_file": source.get("file", ""),
        "extracted_text": source.get("extracted_text", ""),
        "page_count": source.get("page_count"),
    }


def _map_text(document: dict[str, Any]) -> str:
    parts = [str(document.get("title") or ""), str(document.get("summary") or "")]
    for key in ("elements", "properties", "relations", "functions", "open_questions", "questions"):
        value = document.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    parts.extend(str(item.get(field) or "") for field in ("name", "title", "content", "description", "question", "target"))
                else:
                    parts.append(str(item))
    return "\n".join(part for part in parts if part.strip())


def build_legal_corpus(speciality_root: Path) -> dict[str, Any] | None:
    """Create one traceable OKF per extracted article candidate and a searchable index."""
    speciality_root = speciality_root.resolve()
    compiled_root = speciality_root / "source-okfs" / "compiled"
    concepts_root = speciality_root / "source-okfs" / "concepts"
    if not compiled_root.is_dir():
        return None
    source_files = sorted(compiled_root.rglob("*.okf"))
    concept_files = sorted(concepts_root.rglob("*.okf")) if concepts_root.is_dir() else []
    if not source_files:
        return None

    source_hashes = {path: _sha256(path) for path in source_files}
    source_rows = [{"path": path.relative_to(speciality_root).as_posix(), "sha256": source_hashes[path]} for path in source_files]
    concept_rows = [{"path": path.relative_to(speciality_root).as_posix(), "sha256": _sha256(path)} for path in concept_files]
    source_digest = hashlib.sha256(json.dumps({"sources": source_rows, "concepts": concept_rows}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    index_path = speciality_root / "source-okfs" / "provision-index.json"
    current_index = _json(index_path, {})
    if current_index.get("source_digest") == source_digest:
        provision_rows = current_index.get("provisions", [])
        if isinstance(provision_rows, list) and all((speciality_root / row.get("file", "")).is_file() for row in provision_rows if isinstance(row, dict)):
            counts = current_index.get("counts", {})
            return {
                "status": "auto-partitioned-unreviewed",
                "unchanged": True,
                "source_digest": source_digest,
                "index_path": "source-okfs/provision-index.json",
                "documents": counts.get("documents", len(source_files)),
                "article_candidates": counts.get("article_candidates", len(provision_rows)),
                "subdevice_candidates": counts.get("subdevice_candidates", 0),
                "research_maps": counts.get("research_maps", len(concept_files)),
            }

    provisions: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    subdevice_total = 0
    for source_path in source_files:
        document = _json(source_path, {})
        if not isinstance(document, dict) or not str(document.get("schema", "")).startswith("okfforge."):
            continue
        source_id = str(document.get("id") or source_path.stem)
        title = str(document.get("title") or source_id)
        source_rel = source_path.relative_to(speciality_root).as_posix()
        source = _document_source(document)
        elements = [
            row for row in document.get("elements", [])
            if isinstance(row, dict) and ("artigo" in str(row.get("type", "")).casefold() or "article" in str(row.get("type", "")).casefold())
        ] if isinstance(document.get("elements"), list) else []
        groups = _group_article_fragments(elements)
        doc_provisions: list[str] = []
        document_dir = _safe_slug(source_path.relative_to(compiled_root).with_suffix("").as_posix().replace("/", "-"))
        for ordinal, group in enumerate(groups, start=1):
            marker = group["marker"]
            number_match = ARTICLE_RE.search(marker)
            article_number = number_match.group(1) if number_match else ""
            first_element = group["fragments"][0]["element"]
            source_element_ids = [str(part["element"].get("id") or "") for part in group["fragments"]]
            article_id = f"{source_id}#ART-{article_number or 'CANDIDATE'}-{ordinal:04d}"
            subdevices = _split_subdevices(group["text"], article_id)
            subdevice_total += len(subdevices)
            article_file = Path("source-okfs") / "provisions" / document_dir / f"art-{ordinal:04d}.okf"
            article = {
                "schema": "okfforge.juceb.legal_provision.v1",
                "kind": "legal_provision",
                "id": article_id,
                "title": f"{title} — {marker}",
                "jurisdiction": document.get("jurisdiction", "unknown"),
                "topic_key": document.get("topic_key", ""),
                "parent_act_id": source_id,
                "device": {
                    "type": "artigo_candidato",
                    "marker": marker,
                    "number": article_number,
                    "source_element_ids": source_element_ids,
                    "attributes": first_element.get("attributes", {}),
                    "text": group["text"],
                    "subdevices": subdevices,
                },
                "legal_status": {
                    "source_capture": "official_source_captured" if source.get("url") else "source_unverified",
                    "article_boundary": "automatic_candidate_pending_review",
                    "text_status": "empty_candidate" if not group["text"] else "extracted_candidate",
                    "legal_consolidation": "unverified",
                    "validity": "unverified",
                },
                "source": source,
                "relations": [{"type": "parte_de", "target": source_id}],
                "provenance": {
                    "compiled_source": source_rel,
                    "compiled_source_sha256": source_hashes[source_path],
                    "review_status": document.get("review_status", "automatic_extraction_not_legally_consolidated"),
                    "completeness": document.get("completeness", {}),
                },
            }
            output_path = speciality_root / article_file
            _write_json(output_path, article)
            doc_provisions.append(article_id)
            provisions.append({
                "id": article_id,
                "title": article["title"],
                "parent_act_id": source_id,
                "article_marker": marker,
                "article_number": article_number,
                "file": article_file.as_posix(),
                "source_url": source.get("url", ""),
                "source_authority": source.get("authority", ""),
                "review_status": article["legal_status"],
                "text": group["text"],
                "search_text": f"{title} {source_id} {marker} {group['text']}",
            })
        documents.append({
            "id": source_id,
            "title": title,
            "file": source_rel,
            "source_url": source.get("url", ""),
            "source_authority": source.get("authority", ""),
            "source_sha256": source.get("source_sha256", ""),
            "review_status": document.get("review_status", "automatic_extraction_not_legally_consolidated"),
            "completeness": document.get("completeness", {}),
            "provisions": doc_provisions,
        })

    maps: list[dict[str, Any]] = []
    for map_path in concept_files:
        document = _json(map_path, {})
        if not isinstance(document, dict):
            continue
        maps.append({
            "id": str(document.get("id") or map_path.stem),
            "title": str(document.get("title") or map_path.stem),
            "file": map_path.relative_to(speciality_root).as_posix(),
            "review_status": document.get("review_status", "unreviewed_legal_research_map"),
            "linked_sources": document.get("linked_sources", []),
            "search_text": _map_text(document),
        })

    index = {
        "schema": "cognoscere.juceb.provision-index.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_digest": source_digest,
        "partition": "one-OKF-per-extracted-article-candidate",
        "review_status": "automatic_extraction_not_legally_consolidated",
        "counts": {
            "documents": len(documents),
            "article_candidates": len(provisions),
            "subdevice_candidates": subdevice_total,
            "research_maps": len(maps),
        },
        "documents": documents,
        "maps": maps,
        "provisions": provisions,
    }
    _write_json(index_path, index)
    return {
        "status": "auto-partitioned-unreviewed",
        "unchanged": False,
        "source_digest": source_digest,
        "index_path": "source-okfs/provision-index.json",
        **index["counts"],
    }


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode("ascii")
    # NFKD turns Portuguese ordinal markers (º) into a trailing "o".
    return re.sub(r"(?<=\d)o\b", "", normalized)


@lru_cache(maxsize=8)
def _load_index(index_path: str, modified_ns: int, size: int) -> dict[str, Any]:
    del modified_ns, size
    return _json(Path(index_path), {})


def retrieve_legal_evidence(speciality_root: Path, query: str, limit: int = 4) -> list[dict[str, Any]]:
    """Rank article OKFs and thematic maps lexically for citation-grounded Metis context."""
    index_path = speciality_root / "source-okfs" / "provision-index.json"
    if not index_path.is_file():
        return []
    stat = index_path.stat()
    index = _load_index(str(index_path.resolve()), stat.st_mtime_ns, stat.st_size)
    normalized_query = _normalize(query)
    article_match = re.search(r"\bart(?:igo)?\.?\s*(\d+[a-z]?(?:-[a-z])?)\b", normalized_query)
    act_match = re.search(
        r"\b(?:lei(?:\s+complementar)?|lc|decreto(?:-lei)?|resolucao(?:\s+cgsn)?|instrucao\s+normativa|in)\b"
        r"[^\d]{0,32}(\d[\d.]*)\s*/\s*(\d{4})\b",
        normalized_query,
    )
    cited_article = article_match.group(1) if article_match else ""
    cited_act = "".join(re.findall(r"\d+", act_match.group(1))) + act_match.group(2) if act_match else ""
    # Exclude bare digits from fuzzy matching. Act and article numbers receive
    # explicit, structured boosts below, avoiding collisions with years and IDs.
    query_terms = {token for token in TOKEN_RE.findall(normalized_query) if not token.isdigit() and token not in STOP_WORDS and len(token) > 1}
    if not query_terms:
        if not cited_act and not cited_article:
            return []
    ranked: list[tuple[int, dict[str, Any], str]] = []
    for kind, rows in (("provision", index.get("provisions", [])), ("map", index.get("maps", []))):
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = str(row.get("search_text") or row.get("text") or row.get("title") or "")
            tokens = TOKEN_RE.findall(_normalize(text))
            token_set = set(tokens)
            overlap = query_terms & token_set
            score = len(overlap) * 2
            if overlap:
                score += min(5, sum(1 for term in overlap if term in token_set))
            if kind == "provision":
                article_number = str(row.get("article_number") or "")
                parent_act_id = str(row.get("parent_act_id") or "")
                act_numbers = re.findall(r"\d+", parent_act_id)
                row_act = "".join(act_numbers[-2:]) if len(act_numbers) >= 2 else ""
                if cited_act and cited_act == row_act:
                    score += 80
                if cited_article and _normalize(article_number) == cited_article:
                    score += 30 if not cited_act or cited_act == row_act else -20
            elif cited_act:
                linked = row.get("linked_sources", [])
                if any(
                    isinstance(source, dict)
                    and "".join(re.findall(r"\d+", str(source.get("id") or source.get("source_id") or ""))[-2:]) == cited_act
                    for source in linked
                ):
                    score += 20
            if score == 0:
                continue
            ranked.append((score, row, kind))
    ranked.sort(key=lambda item: (item[0], item[1].get("id", "")), reverse=True)
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, Any]] = []
    for score, row, kind in ranked:
        key = (kind, str(row.get("id") or ""))
        if key in seen:
            continue
        seen.add(key)
        if kind == "map":
            results.append({**row, "kind": kind, "score": score})
        else:
            results.append({**row, "kind": kind, "score": score})
        if len(results) >= limit:
            break
    return results
