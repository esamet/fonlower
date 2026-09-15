#!/usr/bin/env python3
"""TEFAS (tefas.gov.tr) resmi JSON API'si icin kucuk, bagimliliksiz istemci.

Iki komut sunar:
  search  - fon adi/kodu metnine gore fon arar (izleme listesine eklerken kullanilir)
  sync    - verilen fon kodu+tipi listesi icin son N gunun fiyat/buyukluk verisini ceker

Sadece Python standart kutuphanesini kullanir (urllib) - cloud routine ortaminda
ekstra bagimlilik kurulumu gerektirmez.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

INFO_URL = "https://www.tefas.gov.tr/api/funds/fonGnlBlgSiraliGetir"

FUND_KINDS = ("YAT", "EMK", "BYF", "GYF", "GSYF")

HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "Origin": "https://www.tefas.gov.tr",
    "Referer": "https://www.tefas.gov.tr/tr/fon-verileri",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

# TEFAS ~6 istek/dakika sinirlar; ardisik istekler arasi bu kadar bekle.
REQUEST_INTERVAL_SEC = 11


def _post(body: dict, max_retry: int = 3) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(INFO_URL, data=data, headers=HEADERS, method="POST")
    last_err = None
    for attempt in range(max_retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(REQUEST_INTERVAL_SEC * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"TEFAS istegi basarisiz: {last_err}")


def _base_body(**overrides) -> dict:
    body = {
        "fonTipi": "YAT",
        "fonKodu": "",
        "aramaMetni": None,
        "fonTurKod": None,
        "fonGrubu": None,
        "sfonTurKod": None,
        "fonTurAciklama": None,
        "kurucuKod": None,
        "basTarih": "",
        "bitTarih": "",
        "basSira": 1,
        "bitSira": 100000,
        "dil": "TR",
        "sFonTurKod": "",
        "fonKod": "",
        "fonGrup": "",
        "fonUnvanTip": "",
    }
    body.update(overrides)
    return body


def _is_empty_marker(data: dict) -> bool:
    msg = (data.get("errorMessage") or "").lower()
    return any(m in msg for m in ("out of bounds", "veri bulunamadi", "veri bulunamadı"))


def search(text: str, kinds=FUND_KINDS, on_date: str | None = None, limit: int = 20):
    """Fon adi veya kodu metnine gore arama yapar; birden fazla fon tipini dener."""
    date_str = on_date or datetime.now().strftime("%Y%m%d")
    results = []
    for kind in kinds:
        body = _base_body(
            fonTipi=kind,
            aramaMetni=text,
            basTarih=date_str,
            bitTarih=date_str,
            bitSira=limit,
        )
        data = _post(body)
        if data.get("errorMessage") and not _is_empty_marker(data):
            continue
        for row in data.get("resultList") or []:
            results.append(
                {
                    "code": row["fonKodu"],
                    "name": row["fonUnvan"],
                    "kind": kind,
                    "price": row.get("fiyat"),
                }
            )
        time.sleep(REQUEST_INTERVAL_SEC)
        if len(results) >= limit:
            break
    return results[:limit]


def sync_one(code: str, kind: str, days: int):
    end = datetime.now()
    start = end - timedelta(days=days)
    body = _base_body(
        fonTipi=kind,
        fonKodu=code,
        basTarih=start.strftime("%Y%m%d"),
        bitTarih=end.strftime("%Y%m%d"),
    )
    data = _post(body)
    if data.get("errorMessage") and not _is_empty_marker(data):
        raise RuntimeError(f"{code}: TEFAS hatasi: {data['errorMessage']}")
    rows = []
    for row in data.get("resultList") or []:
        rows.append(
            {
                "date": row["tarih"],
                "price": row.get("fiyat"),
                "shares_outstanding": row.get("tedPaySayisi"),
                "investor_count": row.get("kisiSayisi"),
                "portfolio_size": row.get("portfoyBuyukluk"),
                "fund_name": row.get("fonUnvan"),
            }
        )
    rows.sort(key=lambda r: r["date"])
    return rows


def sync(watchlist: list[dict], days: int):
    """watchlist: [{"code": "AFA", "kind": "YAT"}, ...]"""
    out = {}
    errors = {}
    for i, entry in enumerate(watchlist):
        code = entry["code"]
        kind = entry.get("kind", "YAT")
        try:
            out[code] = sync_one(code, kind, days)
        except Exception as e:  # noqa: BLE001 - report and continue with other funds
            errors[code] = str(e)
        if i < len(watchlist) - 1:
            time.sleep(REQUEST_INTERVAL_SEC)
    return {"funds": out, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Fon ara")
    p_search.add_argument("text", help="Fon adi veya kodu icinde aranacak metin")
    p_search.add_argument("--limit", type=int, default=20)

    p_sync = sub.add_parser("sync", help="Izleme listesindeki fonlarin son N gununu cek")
    p_sync.add_argument(
        "--watchlist",
        required=True,
        help="JSON dosya yolu ya da '-' (stdin): [{\"code\":..,\"kind\":..}, ...]",
    )
    p_sync.add_argument("--days", type=int, default=10)
    p_sync.add_argument("--out", default="-", help="Cikti dosyasi ('-' ise stdout)")

    args = parser.parse_args()

    if args.command == "search":
        result = search(args.text, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "sync":
        raw = sys.stdin.read() if args.watchlist == "-" else open(args.watchlist, encoding="utf-8").read()
        watchlist = json.loads(raw)
        result = sync(watchlist, args.days)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out == "-":
            print(text)
        else:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)


if __name__ == "__main__":
    main()
