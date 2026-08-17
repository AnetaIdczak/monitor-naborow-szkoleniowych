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
    extract_primary_program_dates,
    is_continuous_intake,
    merge_items,
    normalize_url,
    qualifies_as_current_intake,
    supports_employee_training,
    supports_target_business,
    title_indicates_finished_intake,
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


def test_relevant_dates_keep_both_sides_of_a_window_after_r_abbreviation():
    text = (
        "Wnioski przyjmowane będą od dnia 17.08.2026 r. do 21.08.2026 r. "
        "Wnioski po terminie nie będą rozpatrywane."
    )
    assert extract_relevant_dates(text) == [
        date(2026, 8, 17), date(2026, 8, 21)
    ]


def test_relevant_dates_prefer_application_window_over_publication_date():
    text = (
        "Urząd 31.07.2026 ogłasza nabór. Nabór wniosków będzie trwał "
        "od dnia 17.08.2026 r. do dnia 21.08.2026 r."
    )
    assert extract_relevant_dates(text) == [
        date(2026, 8, 17), date(2026, 8, 21)
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
    assert not title_is_intake("Podsumowanie naboru wniosków KFS 2026")
    assert title_indicates_finished_intake("Podsumowanie naboru wniosków KFS 2026")


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


def test_continuous_warp_intake_is_active_even_when_old_start_date_is_present():
    text = (
        "Nabór skierowany jest do przedsiębiorstw MŚP i ich pracowników. "
        "Nabór jest realizowany w trybie ciągłym od 23.01.2025 r. "
        "Dofinansowanie usług rozwojowych w Bazie Usług Rozwojowych."
    )
    assert is_continuous_intake(text)
    accepted, _, confidence = qualifies_as_current_intake(
        "WARP — Usługi rozwojowe dla Twojego biznesu", text, today=date(2026, 8, 17)
    )
    assert accepted is True
    assert confidence == "wysoka"
    source = Source(
        id="warp", category="BUR", region="wielkopolskie", operator="WARP",
        url="https://warp.org.pl/uslugi", enabled=True, direct=True,
    )
    item = build_item(
        Candidate("WARP — Usługi rozwojowe dla Twojego biznesu", source.url, source),
        text,
        today=date(2026, 8, 17),
    )
    assert item["status"] == "aktywny"
    assert item["program"] == "BUR"


def test_merge_keeps_a_continuous_intake_active_after_its_last_page_update():
    source = Source(
        id="warp", category="BUR", region="wielkopolskie", operator="WARP",
        url="https://warp.org.pl/uslugi", enabled=True, direct=True,
    )
    item = build_item(
        Candidate("WARP – Usługi rozwojowe dla Twojego biznesu", source.url, source),
        "Nabór jest realizowany w trybie ciągłym. Dofinansowanie usług "
        "rozwojowych dla mikro, małych i średnich przedsiębiorstw. "
        "Aktualizacja 2 czerwca 2026 r.",
        today=date(2026, 8, 17),
    )
    merged, _, _ = merge_items([], [item], today=date(2026, 8, 17))
    assert len(merged) == 1
    assert merged[0]["status"] == "aktywny"


def test_direct_official_akademia_hr_offer_is_accepted_with_current_dates():
    text = (
        "Fundusze Europejskie dla Rozwoju Społecznego (FERS). "
        "Dofinansowanie wsparcia przedsiębiorców i pracowników przedsiębiorstw. "
        "Start składania wniosków 25 marca 2024. "
        "Koniec przyjmowania wniosków 30 listopada 2026. "
        "Wsparcie szkoleniowe i doradcze w obszarze HR."
    )
    accepted, dates, confidence = qualifies_as_current_intake(
        "Akademia HR – oferta dla przedsiębiorców",
        text,
        today=date(2026, 8, 17),
        direct_program=True,
    )
    assert accepted is True
    assert dates[-1] == date(2026, 11, 30)
    assert confidence == "wysoka"


def test_direct_feng_business_program_needs_explicit_opt_in():
    text = (
        "Fundusze Europejskie dla Nowoczesnej Gospodarki (FENG). "
        "Start składania wniosków 12 sierpnia 2025. "
        "Koniec przyjmowania wniosków 3 września 2026. "
        "Dofinansowanie dla mikro, małych i średnich przedsiębiorstw. "
        "Szczegóły dofinansowania Inny program kończy się 15 września 2026."
    )
    assert supports_target_business(
        "Granty na Eurogranty", text, include_business_program=True
    )
    rejected, _, _ = qualifies_as_current_intake(
        "Granty na Eurogranty", text, today=date(2026, 8, 17), direct_program=True
    )
    accepted, dates, confidence = qualifies_as_current_intake(
        "Granty na Eurogranty",
        text,
        today=date(2026, 8, 17),
        direct_program=True,
        include_business_program=True,
    )
    assert rejected is False
    assert accepted is True
    assert dates[-1] == date(2026, 9, 3)
    assert confidence == "wysoka"


def test_direct_program_dates_ignore_other_offers_below_program_card():
    text = (
        "8 lipca 2025 Ogłoszenie konkursu 12 sierpnia 2025 "
        "Start składania wniosków 3 września 2026 Koniec przyjmowania wniosków "
        "Szczegóły dofinansowania Inny program kończy się 15 września 2026."
    )
    assert extract_primary_program_dates(text) == [
        date(2025, 7, 8), date(2025, 8, 12), date(2026, 9, 3)
    ]


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
    merged, new_count, changed_count = merge_items(
        [old], [new], today=date(2026, 6, 2)
    )
    assert new_count == 0
    assert changed_count == 1
    assert merged[0]["pierwsze_wykrycie"] == "2026-06-01"
    assert merged[0]["zmieniony"] is True


def test_merge_removes_stale_completed_items_and_deduplicates_asset_entry():
    old = build_item(
        Candidate("Nabór KFS 2026", "https://test.praca.gov.pl/-/old", SOURCE),
        "Nabór trwa od 01.01.2026 do 02.01.2026.",
        today=date(2025, 12, 1),
    )
    first = build_item(
        Candidate("Informacja o planowanym naborze KFS", "https://test.praca.gov.pl/-/a?p_r_p_assetEntryId=77", SOURCE),
        "Nabór KFS dla pracodawców w 2026 roku.",
        today=date(2026, 1, 1),
    )
    duplicate = dict(first)
    duplicate["id"] = "inny-adres"
    duplicate["url"] = "https://test.praca.gov.pl/-/b?p_r_p_assetEntryId=77"
    duplicate["tytul"] = "Informacja o planowanym naborze wniosków KFS dla pracodawców"
    merged, new_count, _ = merge_items(
        [old], [first, duplicate], today=date(2026, 1, 1)
    )
    assert new_count == 1
    assert len(merged) == 1
    assert merged[0]["id"] == "inny-adres"


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url(
        "HTTPS://Example.com//nabor?utm_source=x&id=2#details"
    ) == "https://example.com/nabor?id=2"
