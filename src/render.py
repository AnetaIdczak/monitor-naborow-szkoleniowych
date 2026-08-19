from __future__ import annotations

import html
import json
from datetime import datetime


def render_dashboard(items: list[dict], report: dict) -> str:
    safe_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    generated = report.get("generated_at")
    if generated:
        try:
            generated_label = datetime.fromisoformat(generated).strftime("%d.%m.%Y, %H:%M")
        except ValueError:
            generated_label = generated
    else:
        generated_label = "jeszcze nie uruchomiono"

    return f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Aktualne nabory na dofinansowanie szkoleń pracowników">
  <title>Monitor naborów szkoleniowych</title>
  <style>
    :root {{
      --navy:#132238; --ink:#24364b; --muted:#66778b; --line:#dfe6ee;
      --paper:#fff; --bg:#f4f7fa; --green:#16725b; --blue:#2166a5;
      --amber:#ad6500; --red:#a33b3b; --shadow:0 10px 30px rgba(19,34,56,.08);
    }}
    * {{ box-sizing:border-box }}
    body {{ margin:0; font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;
      color:var(--ink); background:var(--bg); }}
    header {{ background:linear-gradient(125deg,#10233c,#1d5470); color:#fff; padding:42px 22px 34px; }}
    .wrap {{ max-width:1280px; margin:auto; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); letter-spacing:-.035em; }}
    header p {{ max-width:760px; margin:0; color:#dceaf1; line-height:1.55; }}
    .updated {{ display:inline-block; margin-top:16px; padding:7px 11px; border-radius:999px;
      background:rgba(255,255,255,.12); font-size:13px; }}
    main {{ padding:24px 20px 50px; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:18px; }}
    .stat {{ background:var(--paper); border:1px solid var(--line); border-radius:14px;
      padding:18px; box-shadow:var(--shadow); }}
    .stat b {{ display:block; font-size:28px; color:var(--navy); }}
    .stat span {{ font-size:13px; color:var(--muted); }}
    .filters {{ display:grid; grid-template-columns:2fr repeat(5,1fr); gap:10px;
      background:var(--paper); padding:16px; border:1px solid var(--line); border-radius:14px;
      box-shadow:var(--shadow); position:sticky; top:8px; z-index:4; }}
    input,select {{ width:100%; padding:11px 12px; border:1px solid #cbd6e2; border-radius:9px;
      background:#fff; color:var(--ink); font:inherit; }}
    .toolbar {{ display:flex; justify-content:space-between; align-items:center; margin:18px 2px 10px; gap:12px; }}
    .toolbar button {{ border:0; background:var(--navy); color:#fff; padding:10px 14px;
      border-radius:9px; cursor:pointer; font-weight:650; }}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:14px;
      background:var(--paper); box-shadow:var(--shadow); }}
    table {{ border-collapse:collapse; width:100%; min-width:1040px; }}
    th {{ position:sticky; top:0; background:#edf3f7; color:#405468; text-align:left;
      font-size:12px; letter-spacing:.04em; text-transform:uppercase; padding:12px; }}
    td {{ border-top:1px solid var(--line); padding:13px 12px; vertical-align:top; font-size:14px; }}
    tr:hover td {{ background:#f8fbfd; }}
    a {{ color:var(--blue); font-weight:650; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .badge {{ display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px;
      font-weight:700; white-space:nowrap; }}
    .aktywny {{ color:var(--green); background:#e5f5ef; }}
    .zapowiedziany {{ color:var(--blue); background:#e8f1fb; }}
    .zakonczony {{ color:#68727e; background:#edf0f3; }}
    .do-weryfikacji {{ color:var(--amber); background:#fff3dc; }}
    .empty {{ padding:50px 20px; text-align:center; color:var(--muted); display:none; }}
    footer {{ color:var(--muted); font-size:13px; line-height:1.5; padding:20px 2px; }}
    @media (max-width:900px) {{
      .stats {{ grid-template-columns:repeat(2,1fr) }}
      .filters {{ grid-template-columns:1fr 1fr; position:static }}
      .filters input {{ grid-column:1/-1 }}
    }}
    @media (max-width:520px) {{
      .stats {{ grid-template-columns:1fr 1fr }}
      .filters {{ grid-template-columns:1fr }}
      .filters input {{ grid-column:auto }}
      .toolbar {{ align-items:flex-start; flex-direction:column }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>Monitor naborów szkoleniowych</h1>
      <p>KFS, BUR oraz regionalne i krajowe możliwości dofinansowania rozwoju
      pracowników. Domyślnie widoczne są wyłącznie nabory aktywne i zapowiedziane.</p>
      <span class="updated">Ostatnia kontrola: {html.escape(str(generated_label))}</span>
    </div>
  </header>
  <main class="wrap">
    <section class="stats" aria-label="Podsumowanie">
      <div class="stat"><b id="statAll">0</b><span>widoczne nabory</span></div>
      <div class="stat"><b id="statActive">0</b><span>aktywne</span></div>
      <div class="stat"><b id="statUpcoming">0</b><span>zapowiedziane</span></div>
      <div class="stat"><b id="statNew">0</b><span>nowe lub zmienione</span></div>
    </section>
    <section class="filters" aria-label="Filtry">
      <input id="query" type="search" placeholder="Szukaj po nazwie, operatorze lub regionie…">
      <select id="region"><option value="">Wszystkie regiony</option></select>
      <select id="program"><option value="">Wszystkie programy</option></select>
      <select id="status">
        <option value="">Wszystkie statusy</option><option>aktywny</option>
        <option>zapowiedziany</option><option>do weryfikacji</option><option>zakończony</option>
      </select>
      <select id="confidence">
        <option value="">Dowolna wiarygodność</option>
        <option value="wysoka">Wysoka</option>
        <option value="średnia">Średnia</option>
      </select>
      <select id="drive">
        <option value="">Dowolna odległość</option>
        <option value="tak">Do ok. 3 h od Poznania</option>
        <option value="częściowo">Częściowo do 3 h</option>
      </select>
    </section>
    <div class="toolbar">
      <strong id="counter">0 wyników</strong>
      <button type="button" id="download">Pobierz widoczne CSV</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Nabór</th><th>Status</th><th>Program</th><th>Region</th>
          <th>Operator</th><th>Termin</th><th>Wiarygodność</th>
          <th>Dofinansowanie</th><th>Firmy</th><th>BUR</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
      <div class="empty" id="empty">Brak naborów spełniających wybrane kryteria.</div>
    </div>
    <footer>
      Automatyczna klasyfikacja ma charakter informacyjny. Przed przygotowaniem
      wniosku zweryfikuj termin, grupę docelową i zasady w dokumentacji operatora.
      Źródła sprawdzone poprawnie: {int(report.get("sources_ok", 0))} z
      {int(report.get("sources_total", 0))}.
    </footer>
  </main>
  <script>
    const DATA = {safe_json};
    const $ = id => document.getElementById(id);
    const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({{
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }})[char]);
    const slug = value => String(value).normalize("NFD").replace(/[\\u0300-\\u036f]/g,"")
      .toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
    const formatDate = value => value ? new Date(value+"T12:00:00").toLocaleDateString("pl-PL") : "brak danych";
    const formatTerm = row => row.nabor_ciagly ? "nabór ciągły" :
      `${{formatDate(row.data_od)}} – ${{formatDate(row.data_do)}}`;
    const money = value => value ? Number(value).toLocaleString("pl-PL")+" zł" : "—";
    let visible = [];

    function populate(id, key) {{
      [...new Set(DATA.map(row => row[key]).filter(Boolean))].sort()
        .forEach(value => $(id).insertAdjacentHTML("beforeend", `<option>${{esc(value)}}</option>`));
    }}
    populate("region","region"); populate("program","program");

    function apply() {{
      const query = $("query").value.trim().toLocaleLowerCase("pl");
      visible = DATA.filter(row => {{
        const haystack = [row.tytul,row.operator,row.region,row.program,row.typ_firmy]
          .join(" ").toLocaleLowerCase("pl");
        return (!query || haystack.includes(query))
          && (!$("region").value || row.region === $("region").value)
          && (!$("program").value || row.program === $("program").value)
          && (!$("status").value || row.status === $("status").value)
          && (!$("confidence").value || row.wiarygodnosc === $("confidence").value)
          && (!$("drive").value || row.do_3h_od_poznania === $("drive").value)
          && ($("status").value || row.status !== 'do weryfikacji');
      }});
      $("rows").innerHTML = visible.map(row => `<tr>
        <td><a href="${{esc(row.url)}}" target="_blank" rel="noopener">${{esc(row.tytul)}}</a>
          ${{row.nowy ? '<br><span class="badge aktywny">nowy</span>' : ""}}
          ${{row.zmieniony ? '<br><span class="badge zapowiedziany">zmieniony</span>' : ""}}</td>
        <td><span class="badge ${{slug(row.status)}}">${{esc(row.status)}}</span></td>
        <td>${{esc(row.program)}}</td><td>${{esc(row.region)}}</td><td>${{esc(row.operator)}}</td>
        <td>${{formatTerm(row)}}</td>
        <td>${{esc(row.wiarygodnosc || "do weryfikacji")}}</td>
        <td>${{row.dofinansowanie_proc ? esc(row.dofinansowanie_proc)+"% · " : ""}}${{money(row.kwota_max)}}</td>
        <td>${{esc(row.typ_firmy)}}</td><td>${{esc(row.bur)}}</td>
      </tr>`).join("");
      $("empty").style.display = visible.length ? "none" : "block";
      $("counter").textContent = `${{visible.length}} wyników`;
      $("statAll").textContent = visible.length;
      $("statActive").textContent = visible.filter(x => x.status === "aktywny").length;
      $("statUpcoming").textContent = visible.filter(x => x.status === "zapowiedziany").length;
      $("statNew").textContent = visible.filter(x => x.nowy || x.zmieniony).length;
    }}
    document.querySelectorAll("input,select").forEach(element => element.addEventListener("input",apply));
    $("download").addEventListener("click", () => {{
      const fields = ["tytul","program","status","region","operator","data_od","data_do",
        "wiarygodnosc","dofinansowanie_proc","kwota_max","typ_firmy","bur","url"];
      const quote = value => `"${{String(value ?? "").replaceAll('"','""')}}"`;
      const csv = "\\ufeff" + [fields.join(";"), ...visible.map(row => fields.map(key => quote(row[key])).join(";"))].join("\\n");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([csv],{{type:"text/csv;charset=utf-8"}}));
      link.download = "nabory-szkoleniowe.csv"; link.click(); URL.revokeObjectURL(link.href);
    }});
    apply();
  </script>
</body>
</html>
"""
