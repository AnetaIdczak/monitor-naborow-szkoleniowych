from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.render import render_dashboard


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.csv"
JSON_PATH = ROOT / "data" / "nabory.json"
CSV_PATH = ROOT / "data" / "nabory.csv"
REPORT_PATH = ROOT / "data" / "run_report.json"
DOCS_PATH = ROOT / "docs" / "index.html"

USER_AGENT = (
    "MonitorNaborowSzkoleniowych/1.0 "
    "(public-grant-monitor; contact: repository owner on GitHub)"
)
TIMEOUT = int(os.getenv("MONITOR_TIMEOUT_SECONDS", "25"))
MAX_DETAILS_PER_SOURCE = int(os.getenv("MONITOR_MAX_DETAILS_PER_SOURCE", "8"))
REQUEST_DELAY = float(os.getenv("MONITOR_REQUEST_DELAY_SECONDS", "0.15"))

KEYWORDS = (
    "kfs",
    "krajowy fundusz szkoleniowy",
    "rezerwa kfs",
    "usługi rozwojowe",
    "uslugi rozwojowe",
    "baza usług rozwojowych",
    "baza uslug rozwojowych",
    "bur",
    "dofinansowanie szkoleń",
    "dofinansowanie szkolen",
    "szkolenia pracowników",
    "szkolenia pracownikow",
    "kompetencje pracowników",
    "kompetencje pracownikow",
    "kształcenie ustawiczne",
    "ksztalcenie ustawiczne",
    "nabór wniosków",
    "nabor wnioskow",
)

STRONG_KEYWORDS = (
    "kfs",
    "krajowy fundusz szkoleniowy",
    "rezerwa kfs",
    "baza usług rozwojowych",
    "baza uslug rozwojowych",
    "dofinansowanie szkoleń",
    "dofinansowanie szkolen",
    "kształcenie ustawiczne",
    "ksztalcenie ustawiczne",
)

INTAKE_TERMS = (
    "nabór",
    "nabor",
    "rekrutacja",
    "składanie wniosków",
    "skladanie wnioskow",
    "wnioski o przyznanie",
    "rusza",
    "uruchamia",
)

DATE_CONTEXT_TERMS = (
    "nabór",
    "nabor",
    "wniosk",
    "rekrutac",
    "termin",
    "rozpoczę",
    "rozpocze",
    "zakończe",
    "zakoncze",
    "od dnia",
    "do dnia",
)

EXCLUDED_TITLES = (
    "priorytety",
    "wyniki naboru",
    "lista rankingowa",
    "lista wniosków",
    "lista wnioskow",
    "zakończenie naboru",
    "zakonczenie naboru",
    "koniec naboru",
    "unieważnienie",
    "uniewaznienie",
    "informacja o wysokości środków",
    "informacja o wysokosci srodkow",
    "co to jest",
    "power",
    "archiwum",
)

EXCLUDED_LINK_TEXT = (
    "logowanie",
    "polityka prywatności",
    "polityka prywatnosci",
    "deklaracja dostępności",
    "deklaracja dostepnosci",
    "mapa strony",
)

MONTHS = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}

THREE_HOURS_FROM_POZNAN = {
    "wielkopolskie",
    "kujawsko-pomorskie",
    "lubuskie",
}

FARTHER_WEST_POMERANIA = {
    "pup bialogard",
    "pup kolobrzeg",
    "pup koszalin",
    "pup slawno",
    "pup szczecinek",
}

CSV_FIELDS = [
    "id",
    "tytul",
    "program",
    "status",
    "region",
    "operator",
    "data_od",
    "data_do",
    "dofinansowanie_proc",
    "kwota_max",
    "typ_firmy",
    "bur",
    "wiarygodnosc",
    "do_3h_od_poznania",
    "url",
    "pierwsze_wykrycie",
    "ostatnia_weryfikacja",
    "nowy",
    "zmieniony",
]


@dataclass(frozen=True)
class Source:
    id: str
    category: str
    region: str
    operator: str
    url: str
    enabled: bool


@dataclass
class Candidate:
    title: str
    url: str
    source: Source


def simplify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip().lower()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_url(url: str) -> str:
    split = urlsplit(url)
    ignored = {"fbclid", "gclid", "utm_source", "utm_medium", "utm_campaign"}
    query = [(key, value) for key, value in parse_qsl(split.query) if key not in ignored]
    path = re.sub(r"/{2,}", "/", split.path or "/")
    return urlunsplit(
        (split.scheme.lower(), split.netloc.lower(), path, urlencode(query), "")
    )


def stable_id(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def load_sources(path: Path = SOURCES_PATH) -> list[Source]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            Source(
                id=row["id"].strip(),
                category=row["category"].strip(),
                region=row["region"].strip(),
                operator=row["operator"].strip(),
                url=row["url"].strip(),
                enabled=simplify(row.get("enabled", "true")) in {"true", "1", "tak"},
            )
            for row in rows
            if row.get("url", "").strip()
        ]


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
        }
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    if len(response.content) > 15_000_000:
        raise ValueError("Odpowiedź przekracza limit 15 MB")
    time.sleep(REQUEST_DELAY)
    return response


def is_relevant(value: str, *, strong: bool = False) -> bool:
    haystack = simplify(value)
    keywords = STRONG_KEYWORDS if strong else KEYWORDS
    return any(simplify(keyword) in haystack for keyword in keywords)


def extract_candidates(html: str, source: Source) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Candidate] = {}
    for anchor in soup.select("a[href]"):
        href = clean_text(anchor.get("href", ""))
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        parent = anchor.parent
        context = ""
        if parent and parent.name in {"article", "li", "div", "section"}:
            parent_text = clean_text(parent.get_text(" ", strip=True))
            if len(parent_text) <= 700:
                context = parent_text
        combined = f"{title} {href} {context}"
        if not is_relevant(combined):
            continue
        if any(item in simplify(title) for item in EXCLUDED_LINK_TEXT):
            continue
        url = normalize_url(urljoin(source.url, href))
        if urlsplit(url).scheme not in {"http", "https"}:
            continue
        if len(title) < 8:
            title = clean_text(context)[:180] or source.operator
        found[url] = Candidate(title=title[:300], url=url, source=source)

    return sorted(
        found.values(),
        key=lambda item: (
            not is_relevant(item.title, strong=True),
            len(item.title),
        ),
    )[:MAX_DETAILS_PER_SOURCE]


def response_to_text(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or response.url.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(response.content))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:80])
    response.encoding = response.encoding or response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(
        ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside"]
    ):
        element.decompose()
    selectors = (
        ".journal-content-article",
        "[class*='journal-content']",
        "article",
        "main",
    )
    for selector in selectors:
        blocks = soup.select(selector)
        usable = [
            (len(clean_text(block.get_text(" ", strip=True))), block)
            for block in blocks
            if len(clean_text(block.get_text(" ", strip=True))) >= 150
        ]
        if usable:
            return clean_text(max(usable, key=lambda entry: entry[0])[1].get_text(" ", strip=True))
    return clean_text((soup.body or soup).get_text(" ", strip=True))


def extract_dates(text: str) -> list[date]:
    results: set[date] = set()
    for day, month, year in re.findall(
        r"(?<!\d)([0-3]?\d)[.\-/]([01]?\d)[.\-/](20\d{2})(?!\d)", text
    ):
        try:
            results.add(date(int(year), int(month), int(day)))
        except ValueError:
            continue

    month_pattern = "|".join(re.escape(month) for month in MONTHS)
    for day, month_name, year in re.findall(
        rf"(?<!\d)([0-3]?\d)\s+({month_pattern})\s+(20\d{{2}})", simplify(text)
    ):
        try:
            results.add(date(int(year), MONTHS[month_name], int(day)))
        except ValueError:
            continue
    return sorted(results)


def relevant_date_context(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", clean_text(text))
    selected: list[str] = []
    for sentence in sentences:
        normalized = simplify(sentence)
        if any(term in normalized for term in DATE_CONTEXT_TERMS):
            selected.append(sentence)
    return " ".join(dict.fromkeys(selected))


def extract_relevant_dates(text: str) -> list[date]:
    context = relevant_date_context(text)
    if not context:
        return []
    return extract_dates(context)


def contextual_fragments(text: str, signals: tuple[str, ...]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", clean_text(text))
    return " ".join(
        sentence
        for sentence in sentences
        if any(signal in simplify(sentence) for signal in signals)
    )


def extract_percentage(text: str) -> int | None:
    context = contextual_fragments(
        text,
        (
            "dofinansowan",
            "refundac",
            "wkład własny",
            "wklad wlasny",
            "poziom wsparcia",
        ),
    )
    values = [int(value) for value in re.findall(r"(?<!\d)(\d{1,3})\s*%", context)]
    values = [value for value in values if 1 <= value <= 100]
    return max(values) if values else None


def extract_amount(text: str) -> int | None:
    context = contextual_fragments(
        text,
        (
            "maksymal",
            "na jednego pracodawc",
            "na przedsiębior",
            "na przedsiebior",
            "limit dofinansowania",
            "wartość dofinansowania",
            "wartosc dofinansowania",
        ),
    )
    matches = re.findall(
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+(?:,\d{1,2})?|\d{4,7})\s*(?:zł|pln)",
        simplify(context),
    )
    values: list[int] = []
    for value in matches:
        normalized = re.sub(r"[ .]", "", value).replace(",", ".")
        try:
            amount = int(float(normalized))
        except ValueError:
            continue
        if 1_000 <= amount <= 100_000_000:
            values.append(amount)
    return max(values) if values else None


def classify_program(text: str, source: Source) -> str:
    normalized = simplify(text)
    if "krajowy fundusz szkoleniowy" in normalized or re.search(
        r"\bkfs\b", normalized
    ):
        return "KFS"
    if "baza uslug rozwojowych" in normalized or re.search(r"\bbur\b", normalized):
        return "BUR"
    if "fers" in normalized or "fundusze europejskie dla rozwoju spolecznego" in normalized:
        return "FERS"
    if source.category == "regionalne":
        return "Regionalne"
    return source.category


def classify_company_type(text: str) -> str:
    normalized = simplify(text)
    types: list[str] = []
    if re.search(r"\bmikro", normalized):
        types.append("mikro")
    if re.search(r"\bmale\b|\bmalych\b", normalized):
        types.append("małe")
    if re.search(r"\bsredni", normalized):
        types.append("średnie")
    if re.search(r"\bduz", normalized):
        types.append("duże")
    if "msp" in normalized or "msme" in normalized:
        for item in ("mikro", "małe", "średnie"):
            if item not in types:
                types.append(item)
    return ", ".join(types) if types else "do weryfikacji"


def determine_status(start: date | None, end: date | None, today: date) -> str:
    if start and today < start:
        return "zapowiedziany"
    if end and today > end:
        return "zakończony"
    if end:
        return "aktywny"
    if start:
        return "do weryfikacji"
    return "do weryfikacji"


def title_is_intake(title: str) -> bool:
    normalized = simplify(title)
    return (
        any(term in normalized for term in INTAKE_TERMS)
        and not any(term in normalized for term in EXCLUDED_TITLES)
    )


def title_has_outdated_year(title: str, today: date) -> bool:
    years = [int(year) for year in re.findall(r"\b20\d{2}\b", title)]
    return bool(years) and max(years) < today.year


def supports_employee_training(title: str, text: str) -> bool:
    combined = simplify(f"{title} {text[:8000]}")
    if (
        "krajow" in combined
        and "fundusz" in combined
        and "szkoleniow" in combined
    ) or re.search(r"\bkfs\b", combined):
        return True
    training_signal = any(
        signal in combined
        for signal in (
            "baza uslug rozwojowych",
            "uslugi rozwojowe",
            "dofinansowanie szkolen",
            "szkolenia pracownik",
            "rozwoj kompetencji",
            "ksztalcenie ustawiczne",
        )
    )
    business_signal = any(
        signal in combined
        for signal in (
            "pracodawc",
            "pracownik",
            "przedsiebior",
            "firm",
            "msp",
            "duzych firm",
        )
    )
    return training_signal and business_signal


def qualifies_as_current_intake(
    title: str,
    text: str,
    *,
    today: date,
) -> tuple[bool, list[date], str]:
    if (
        not title_is_intake(title)
        or title_has_outdated_year(title, today)
        or not supports_employee_training(title, text)
    ):
        return False, [], "niska"
    dates = [
        value
        for value in extract_relevant_dates(text)
        if today.year - 1 <= value.year <= today.year + 3
    ]
    if dates and dates[-1] < today:
        return False, dates, "niska"
    if len(dates) >= 2 and dates[-1] >= today:
        return True, dates, "wysoka"
    if dates and dates[0] >= today:
        return True, dates, "wysoka"
    if str(today.year) in f"{title} {text[:2500]}":
        return True, dates, "średnia"
    return False, dates, "niska"


def content_fingerprint(item: dict) -> str:
    keys = (
        "tytul",
        "program",
        "region",
        "operator",
        "data_od",
        "data_do",
        "dofinansowanie_proc",
        "kwota_max",
        "typ_firmy",
        "bur",
        "wiarygodnosc",
    )
    payload = json.dumps(
        {key: item.get(key) for key in keys},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_item(
    candidate: Candidate,
    text: str,
    *,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    qualified, relevant_dates, confidence = qualifies_as_current_intake(
        candidate.title,
        text,
        today=today,
    )
    if not qualified:
        raise ValueError("Ogłoszenie nie jest aktualnym naborem")
    start = relevant_dates[0] if relevant_dates else None
    end = relevant_dates[-1] if len(relevant_dates) > 1 else (
        relevant_dates[0] if relevant_dates else None
    )
    title = candidate.title
    if title.lower().endswith(".pdf") and text:
        title = clean_text(text)[:180]
    normalized = simplify(text)
    operator_simple = simplify(candidate.source.operator)
    if candidate.source.region in THREE_HOURS_FROM_POZNAN:
        drive_area = "tak"
    elif candidate.source.region == "zachodniopomorskie":
        drive_area = (
            "nie"
            if operator_simple in FARTHER_WEST_POMERANIA
            else ("częściowo" if not operator_simple.startswith("pup ") else "tak")
        )
    else:
        drive_area = "nie"

    item = {
        "id": stable_id(candidate.url),
        "tytul": title,
        "program": classify_program(f"{title} {text[:8000]}", candidate.source),
        "status": determine_status(start, end, today),
        "region": candidate.source.region,
        "operator": candidate.source.operator,
        "data_od": start.isoformat() if start else "",
        "data_do": end.isoformat() if end else "",
        "dofinansowanie_proc": extract_percentage(text),
        "kwota_max": extract_amount(text),
        "typ_firmy": classify_company_type(text),
        "bur": "tak" if (
            "baza uslug rozwojowych" in normalized
            or re.search(r"\bbur\b", normalized)
        ) else "nieokreślone",
        "wiarygodnosc": confidence,
        "do_3h_od_poznania": drive_area,
        "url": normalize_url(candidate.url),
        "pierwsze_wykrycie": today.isoformat(),
        "ostatnia_weryfikacja": today.isoformat(),
        "nowy": True,
        "zmieniony": False,
    }
    item["content_hash"] = content_fingerprint(item)
    return item


def merge_items(existing: Iterable[dict], discovered: Iterable[dict]) -> tuple[list[dict], int, int]:
    discovered = list(discovered)
    discovered_ids = {item["id"] for item in discovered}
    merged = {item["id"]: dict(item) for item in existing}
    new_count = 0
    changed_count = 0
    for item in discovered:
        previous = merged.get(item["id"])
        if previous is None:
            item["nowy"] = True
            item["zmieniony"] = False
            merged[item["id"]] = item
            new_count += 1
            continue
        changed = previous.get("content_hash") != item.get("content_hash")
        first_seen = previous.get("pierwsze_wykrycie") or item["pierwsze_wykrycie"]
        previous.update(item)
        previous["pierwsze_wykrycie"] = first_seen
        previous["nowy"] = False
        previous["zmieniony"] = changed
        merged[item["id"]] = previous
        changed_count += int(changed)

    today = date.today()
    for item in merged.values():
        if item["id"] not in discovered_ids:
            item["nowy"] = False
            item["zmieniony"] = False
        start = date.fromisoformat(item["data_od"]) if item.get("data_od") else None
        end = date.fromisoformat(item["data_do"]) if item.get("data_do") else None
        item["status"] = determine_status(start, end, today)

    result = sorted(
        merged.values(),
        key=lambda item: (
            item.get("status") == "zakończony",
            item.get("data_do") or "9999-12-31",
            item.get("tytul", ""),
        ),
    )
    return result, new_count, changed_count


def load_existing() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    try:
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logging.exception("Nie udało się odczytać poprzednich danych")
        return []


def save_results(items: list[dict], report: dict) -> None:
    JSON_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DOCS_PATH.write_text(render_dashboard(items, report), encoding="utf-8")


def run() -> dict:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    sources = [source for source in load_sources() if source.enabled]
    existing = load_existing()
    existing_urls = {item.get("url") for item in existing}
    discovered: list[dict] = []
    errors: list[dict] = []
    sources_ok = 0
    candidates_total = 0
    session = create_session()

    for index, source in enumerate(sources, start=1):
        logging.info("[%s/%s] %s", index, len(sources), source.operator)
        try:
            listing_response = fetch(session, source.url)
            listing_response.encoding = (
                listing_response.encoding or listing_response.apparent_encoding
            )
            candidates = extract_candidates(listing_response.text, source)
            sources_ok += 1
            candidates_total += len(candidates)
        except Exception as exc:  # każda awaria źródła jest raportowana osobno
            logging.warning("Błąd źródła %s: %s", source.url, exc)
            errors.append(
                {
                    "source": source.id,
                    "operator": source.operator,
                    "url": source.url,
                    "error": str(exc)[:300],
                }
            )
            continue

        for candidate in candidates:
            try:
                response = fetch(session, candidate.url)
                text = response_to_text(response)
                if not is_relevant(f"{candidate.title} {text[:12000]}", strong=True):
                    continue
                try:
                    item = build_item(candidate, text)
                except ValueError as exc:
                    if str(exc) == "Ogłoszenie nie jest aktualnym naborem":
                        continue
                    raise
                discovered.append(item)
            except Exception as exc:
                logging.warning("Błąd dokumentu %s: %s", candidate.url, exc)
                errors.append(
                    {
                        "source": source.id,
                        "operator": source.operator,
                        "url": candidate.url,
                        "error": str(exc)[:300],
                    }
                )

    merged, new_count, changed_count = merge_items(existing, discovered)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources_total": len(sources),
        "sources_ok": sources_ok,
        "sources_failed": len(sources) - sources_ok,
        "candidates_found": candidates_total,
        "items_verified": len(discovered),
        "items_total": len(merged),
        "new_items": new_count,
        "changed_items": changed_count,
        "known_urls_before_run": len(existing_urls),
        "errors": errors[:100],
    }
    save_results(merged, report)
    logging.info(
        "Gotowe: %s rekordów, %s nowych, %s zmienionych",
        len(merged),
        new_count,
        changed_count,
    )
    return report


if __name__ == "__main__":
    run()
