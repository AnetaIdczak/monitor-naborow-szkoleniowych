from datetime import date

from src.monitor import (
    Candidate,
    Source,
    build_item,
    determine_status,
    extract_amount,
    extract_candidates,
    extract_dates,
    extract_relevant_dates,
    extract_percentage,
    merge_items,
    normalize_url,
    qualifies_as_current_intake,
    supports_employee_training,
    title_is_intake,
)


SOURCE = Source(
    id="test",
    category="KFS",
    region="wielkopolskie",
    operator="PUP Test",
    url="https://test.praca.gov.pl/strona-glowna",
    enabled=True,
)


def test_extract_candidates_selects_relevant_links():
    html = """
    <main>
      <a href="/-/nabor-kfs-2026">Nabór wniosków KFS 2026</a>
      <a href="/kontakt">Kontakt z urzędem</a>
      <a href="/-/szkolenia">Dofinansowanie szkoleń pracowników</a>
    </main>
    """
    results = extract_candidates(html, SOURCE)
    assert [item.title for item in results] == [
        "Nabór wniosków KFS 2026",
        "Dofinansowanie szkoleń pracowników",
    ]


def test_extract_polish_dates_amount_and_percentage():
    text = (
        "Nabór trwa od 8.06.2026 do 12 czerwca 2026 r. "
        "Dofinansowanie 80%, maksymalnie 120 000,00 zł."
    )
    assert extract_dates(text) == [date(2026, 6, 8), date(2026, 6, 12)]
    assert extract_percentage(text) == 80
    assert extract_amount(text) == 120_000


def test_relevant_dates_ignore_footer_and_unrelated_dates():
    text = (
        "Artykuł opublikowano 20.03.2025. "
        "Nabór wniosków będzie prowadzony od 08.06.2026 do 12.06.2026. "
        "Aktualizacja serwisu 30.07.2026."
    )
    assert extract_relevant_dates(text) == [
        date(2026, 6, 8),
        date(2026, 6, 12),
    ]


def test_percentage_and_amount_require_funding_context():
    text = (
        "Identyfikator 57377. Spotkanie 8%. "
        "Maksymalna wartość dofinansowania na jednego pracodawcę to 50 000 zł. "
        "Poziom dofinansowania wynosi 80%."
    )
    assert extract_amount(text) == 50_000
    assert extract_percentage(text) == 80


def test_titles_exclude_information_archives_and_old_programs():
    assert title_is_intake("Nabór wniosków KFS 2026")
    assert not title_is_intake("Priorytety KFS na 2026 rok")
    assert not title_is_intake("Zakończenie naboru KFS")
    assert not title_is_intake("Nabór wniosków w ramach POWER")


def test_employee_training_scope_rejects_individual_education_bon():
    assert supports_employee_training(
        "Nabór KFS 2026",
        "Finansowanie kształcenia ustawicznego pracowników i pracodawców.",
    )
    assert not supports_employee_training(
        "Nabór bonów na kształcenie ustawiczne",
        "Bon dla osoby bezrobotnej podejmującej naukę.",
    )


def test_current_intake_rejects_expired_and_accepts_future():
    expired = (
        "Nabór KFS dla pracodawców trwa od 01.02.2026 do 05.02.2026."
    )
    future = (
        "Nabór KFS dla pracodawców trwa od 01.08.2026 do 05.08.2026."
    )
    assert qualifies_as_current_intake(
        "Nabór wniosków KFS 2026", expired, today=date(2026, 7, 30)
    )[0] is False
    accepted, dates, confidence = qualifies_as_current_intake(
        "Nabór wniosków KFS 2026", future, today=date(2026, 7, 30)
    )
    assert accepted is True
    assert dates[-1] == date(2026, 8, 5)
    assert confidence == "wysoka"


def test_build_item_classifies_kfs_and_status():
    candidate = Candidate(
        title="Nabór Krajowego Funduszu Szkoleniowego",
        url="https://test.praca.gov.pl/-/nabor-kfs",
        source=SOURCE,
    )
    item = build_item(
        candidate,
        "Wnioski od 8.06.2026 do 12.06.2026. Mikro, małe i średnie firmy. "
        "Dofinansowanie wynosi 80%.",
        today=date(2026, 6, 9),
    )
    assert item["program"] == "KFS"
    assert item["status"] == "aktywny"
    assert item["do_3h_od_poznania"] == "tak"
    assert "mikro" in item["typ_firmy"]
    assert item["dofinansowanie_proc"] == 80
    assert item["wiarygodnosc"] == "wysoka"
    assert item["nowy"] is True


def test_determine_status():
    today = date(2026, 7, 30)
    assert determine_status(date(2026, 8, 1), date(2026, 8, 4), today) == "zapowiedziany"
    assert determine_status(date(2026, 7, 1), date(2026, 8, 4), today) == "aktywny"
    assert determine_status(date(2026, 7, 1), date(2026, 7, 20), today) == "zakończony"
    assert determine_status(None, None, today) == "do weryfikacji"


def test_merge_preserves_first_seen_and_marks_change():
    candidate = Candidate(
        title="Nabór KFS",
        url="https://test.praca.gov.pl/-/nabor-kfs",
        source=SOURCE,
    )
    old = build_item(candidate, "Nabór 8.06.2026–12.06.2026. 80%.", today=date(2026, 6, 1))
    new = build_item(candidate, "Nabór 8.06.2026–15.06.2026. 80%.", today=date(2026, 6, 2))
    merged, new_count, changed_count = merge_items([old], [new])
    assert new_count == 0
    assert changed_count == 1
    assert merged[0]["pierwsze_wykrycie"] == "2026-06-01"
    assert merged[0]["zmieniony"] is True


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url(
        "HTTPS://Example.com//nabor?utm_source=x&id=2#details"
    ) == "https://example.com/nabor?id=2"
