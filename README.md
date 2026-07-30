# Monitor naborów szkoleniowych

Bezpłatny monitoring publicznych naborów na dofinansowanie szkoleń dla
pracowników. Projekt sprawdza oficjalne strony dwa razy w tygodniu, porządkuje
wyniki i publikuje czytelny panel.

## Zakres

- Krajowy Fundusz Szkoleniowy (KFS i rezerwa KFS),
- Baza Usług Rozwojowych i operatorzy regionalni,
- regionalne i krajowe nabory Funduszy Europejskich,
- PARP i programy FERS,
- województwa: wielkopolskie, kujawsko-pomorskie, zachodniopomorskie
  i lubuskie,
- dodatkowy filtr obszaru sprzedażowego do około 3 godzin od Poznania.

## Jak działa

1. GitHub Actions uruchamia `python -m src.monitor` w poniedziałek i czwartek.
2. Skrypt pobiera wyłącznie strony wskazane w `config/sources.csv`.
3. Wyszukuje odnośniki związane z KFS, BUR, szkoleniami i dofinansowaniem.
4. Odrzuca archiwalne wpisy, priorytety, wyniki i informacje ogólne.
5. Nadaje wynikom poziom wiarygodności na podstawie tytułu i terminu.
6. Zapisuje wyniki w `data/nabory.json` i `data/nabory.csv`.
7. Generuje panel `docs/index.html`.
8. GitHub Pages publikuje panel po każdej zmianie.

## Uruchomienie ręczne

Nie trzeba instalować Pythona na komputerze. W repozytorium wybierz:

`Actions` → `Monitor naborów` → `Run workflow`.

## Konfiguracja GitHub Pages

Po połączeniu zmian z gałęzią `main`:

1. otwórz `Settings` → `Pages`,
2. w sekcji `Build and deployment` wybierz `GitHub Actions`,
3. uruchom workflow `Publikacja panelu`.

## Uruchomienie lokalne (opcjonalne)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.monitor
python -m http.server 8000 --directory docs
```

Panel będzie dostępny pod `http://localhost:8000`.

## Bezpieczeństwo i wiarygodność

Projekt przechowuje tylko dane publiczne. Każdy rekord zawiera link do
oficjalnego źródła oraz datę ostatniej weryfikacji. Automatyczna klasyfikacja
jest pomocą w wyszukiwaniu, a nie potwierdzeniem kwalifikowalności firmy.
Przed złożeniem wniosku należy przeczytać regulamin i dokumentację operatora.
