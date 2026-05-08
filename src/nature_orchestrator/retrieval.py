from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from .io import write_text, write_yaml


SearchBackend = Callable[[str], Iterable[dict[str, Any]]]
FetchBackend = Callable[[str], dict[str, Any]]


def normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def parse_date(value: str) -> date | None:
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def compact_identifier(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def fingerprint_identifiers(fingerprint: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["doi", "doi_suffix", "slug", "article_url", "title"]:
        if fingerprint.get(key):
            values.append(str(fingerprint[key]))
    values.extend(str(item) for item in fingerprint.get("known_preprints") or [] if item)
    return sorted(set(values), key=len, reverse=True)


def identifier_hits(text: str, fingerprint: dict[str, Any]) -> list[str]:
    lower = text.lower()
    compact = compact_identifier(text)
    hits: list[str] = []
    for identifier in fingerprint_identifiers(fingerprint):
        ident_lower = identifier.lower()
        if ident_lower and (ident_lower in lower or compact_identifier(identifier) in compact):
            hits.append(identifier)
    return hits


def title_ngram_hits(text: str, fingerprint: dict[str, Any]) -> list[str]:
    normalized = normalize_text(text)
    hits = []
    for gram in fingerprint.get("title_ngrams") or []:
        normalized_gram = normalize_text(str(gram))
        if normalized_gram and normalized_gram in normalized:
            hits.append(str(gram))
    return hits


def author_combo_hit(text: str, fingerprint: dict[str, Any]) -> bool:
    normalized = normalize_text(text)
    surnames = [str(item).lower() for item in fingerprint.get("author_surnames") or [] if item]
    surname_count = sum(1 for surname in surnames if re.search(rf"\b{re.escape(surname)}\b", normalized))
    if surname_count < 2:
        return False
    title_words = set(normalize_text(str(fingerprint.get("title") or "")).split())
    distinctive = {word for word in title_words if len(word) >= 5}
    return bool(distinctive.intersection(normalized.split()))


def block_decision(reason: str, **extra: Any) -> dict[str, Any]:
    decision = {"allowed": False, "reasons": [reason]}
    decision.update(extra)
    return decision


def allow_decision(**extra: Any) -> dict[str, Any]:
    decision = {"allowed": True, "reasons": []}
    decision.update(extra)
    return decision


def filter_query(query: str, fingerprint: dict[str, Any]) -> dict[str, Any]:
    if identifier_hits(query, fingerprint):
        return block_decision("query contains target identifier")
    if title_ngram_hits(query, fingerprint):
        return block_decision("query contains target title n-gram")
    if author_combo_hit(query, fingerprint):
        return block_decision("query contains target author combination")
    normalized = normalize_text(query)
    title_hit = bool(title_ngram_hits(query, fingerprint))
    if title_hit and any(source in normalized for source in ["arxiv", "biorxiv", "medrxiv"]):
        return block_decision("query combines target title with preprint source")
    return allow_decision(query=query)


def filter_search_result(result: dict[str, Any], fingerprint: dict[str, Any]) -> dict[str, Any]:
    title = str(result.get("title") or "")
    url = str(result.get("url") or "")
    snippet = str(result.get("snippet") or "")
    combined = "\n".join([title, url, snippet])
    if identifier_hits(combined, fingerprint):
        return block_decision("result contains target identifier", title=title, url=url)
    if title_ngram_hits(combined, fingerprint):
        return block_decision("result contains target title n-gram", title=title, url=url)
    if author_combo_hit(combined, fingerprint):
        return block_decision("result contains target author combination", title=title, url=url)

    result_date = parse_date(str(result.get("date") or result.get("published") or ""))
    cutoff = parse_date(str(fingerprint.get("publication_date") or ""))
    if result_date and cutoff and result_date > cutoff:
        return block_decision("result is after target publication date", title=title, url=url, date=str(result_date))
    return allow_decision(title=title, url=url, snippet=snippet, date=str(result.get("date") or ""))


def safe_excerpt(text: str, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def document_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def filter_fetched_document(document: dict[str, Any], fingerprint: dict[str, Any]) -> dict[str, Any]:
    title = str(document.get("title") or "")
    url = str(document.get("url") or "")
    text = str(document.get("text") or "")
    combined = "\n".join([title, url, text])
    if identifier_hits(combined, fingerprint):
        return block_decision("fetched page contains target identifier", title=title, url=url, sha256=document_hash(combined))
    if title_ngram_hits(combined, fingerprint):
        return block_decision("fetched page contains target title n-gram", title=title, url=url, sha256=document_hash(combined))
    if author_combo_hit(combined, fingerprint):
        return block_decision("fetched page contains target author combination", title=title, url=url, sha256=document_hash(combined))
    return allow_decision(
        title=title,
        url=url,
        date=str(document.get("date") or ""),
        snippet=str(document.get("snippet") or ""),
        excerpt=safe_excerpt(text),
        sha256=document_hash(combined),
    )


def safe_search(
    query_requests: list[dict[str, Any]],
    fingerprint: dict[str, Any],
    *,
    search_backend: SearchBackend | None = None,
    fetch_backend: FetchBackend | None = None,
) -> dict[str, Any]:
    pack: dict[str, Any] = {
        "schema_version": "nature_orchestrator.literature_pack.v1",
        "mode": "safe_web",
        "kept_documents": [],
        "blocked_queries": [],
        "blocked_documents": [],
        "retrieval_log": [],
    }
    for request in query_requests:
        query = str(request.get("query") or "")
        query_decision = filter_query(query, fingerprint)
        log_item: dict[str, Any] = {"query": query, "query_decision": query_decision, "results": []}
        if not query_decision["allowed"]:
            pack["blocked_queries"].append({"query": query, "reasons": query_decision["reasons"]})
            pack["retrieval_log"].append(log_item)
            continue
        if search_backend is None:
            log_item["backend_status"] = "not_configured"
            pack["retrieval_log"].append(log_item)
            continue

        for result in search_backend(query):
            result_decision = filter_search_result(dict(result), fingerprint)
            log_result = {"title": result.get("title") or "", "url": result.get("url") or "", "decision": result_decision}
            log_item["results"].append(log_result)
            if not result_decision["allowed"]:
                pack["blocked_documents"].append(
                    {
                        "title": result_decision.get("title") or "",
                        "url": result_decision.get("url") or "",
                        "reasons": result_decision["reasons"],
                    }
                )
                continue

            if "text" in result:
                document = dict(result)
            elif fetch_backend is not None:
                document = fetch_backend(str(result.get("url") or ""))
                document.setdefault("title", result.get("title") or "")
                document.setdefault("url", result.get("url") or "")
                document.setdefault("snippet", result.get("snippet") or "")
                document.setdefault("date", result.get("date") or "")
            else:
                document = dict(result)
                document["text"] = str(result.get("snippet") or "")

            fetch_decision = filter_fetched_document(document, fingerprint)
            log_result["fetch_decision"] = fetch_decision
            if fetch_decision["allowed"]:
                pack["kept_documents"].append(
                    {
                        "title": fetch_decision["title"],
                        "url": fetch_decision["url"],
                        "date": fetch_decision.get("date") or result_decision.get("date") or "",
                        "snippet": fetch_decision.get("snippet") or result_decision.get("snippet") or "",
                        "excerpt": fetch_decision.get("excerpt") or "",
                        "sha256": fetch_decision.get("sha256") or "",
                        "why_allowed": "passed query, result, and fetch guards",
                    }
                )
            else:
                pack["blocked_documents"].append(
                    {
                        "title": fetch_decision.get("title") or result_decision.get("title") or "",
                        "url": fetch_decision.get("url") or result_decision.get("url") or "",
                        "sha256": fetch_decision.get("sha256") or "",
                        "reasons": fetch_decision["reasons"],
                    }
                )
        pack["retrieval_log"].append(log_item)
    return pack


def offline_literature_pack() -> dict[str, Any]:
    return {
        "schema_version": "nature_orchestrator.literature_pack.v1",
        "mode": "official_offline",
        "kept_documents": [],
        "blocked_queries": [],
        "blocked_documents": [],
        "retrieval_log": [],
    }


def write_literature_artifacts(out_dir: Path, pack: dict[str, Any]) -> None:
    write_yaml(out_dir / "retrieval" / "literature_pack.yaml", pack)
    write_yaml(
        out_dir / "retrieval" / "retrieval_log.yaml",
        {
            "schema_version": "nature_orchestrator.retrieval_log.v1",
            "mode": pack.get("mode"),
            "retrieval_log": pack.get("retrieval_log") or [],
            "blocked_queries": pack.get("blocked_queries") or [],
            "blocked_documents": pack.get("blocked_documents") or [],
        },
    )
    lines = [
        "# Network Leakage Report",
        "",
        f"Mode: `{pack.get('mode')}`",
        f"Kept documents: `{len(pack.get('kept_documents') or [])}`",
        f"Blocked queries: `{len(pack.get('blocked_queries') or [])}`",
        f"Blocked documents: `{len(pack.get('blocked_documents') or [])}`",
    ]
    write_text(out_dir / "retrieval" / "network_leakage_report.md", "\n".join(lines) + "\n")
