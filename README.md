# Co robi władza? (corobiwladza.pl) – prototyp dla Gdyni

Niezależny serwis, który tłumaczy decyzje władzy na prosty język: jak jest
i co to zmienia dla mieszkańca. Ten prototyp pokazuje **ostatnią sesję Rady
Miasta Gdyni**: uchwały, głosowania imienne i opis prostym językiem.

**Stan danych:** XXXVI sesja Rady Miasta Gdyni z 28 października 2026 r.,
42 uchwały, 28 radnych. Dane pobrane z BIP 12.11.2026.

## Zasady

- Tylko fakty, bez ocen. Te same reguły dla każdego klubu.
- Każda liczba i każde zdanie ma źródło (link do PDF w BIP; przy opisach
  także cytaty sprawdzane automatycznie).
- Dane osobowe: wyłącznie publiczna działalność radnych (imię i nazwisko,
  funkcja, klub, głosowania). Bez zdjęć, życiorysów i danych kontaktowych.
- Niezgodność w danych to błąd, który zatrzymuje budowę, a nie ostrzeżenie.
- Kolory strony tylko w skali szarości, bez barw partyjnych.

## Szybki start

Wymagania: Python 3.10+ (bez dodatkowych bibliotek) i `pdftotext`/`pdfinfo`
(pakiet `poppler-utils`).

```bash
python3 -m corobiwladza pobierz          # ostatnia sesja z BIP -> data/gdynia/sesje/*.json
python3 -m corobiwladza pobierz --offline  # to samo wyłącznie z lokalnego cache
python3 -m corobiwladza strona           # sprawdza opisy i buduje stronę w site/
python3 -m unittest -v                   # testy sprawdzeń
```

Stronę otwiera się z pliku `site/index.html`. Nie ładuje niczego z zewnątrz
i działa bez JavaScriptu (skrypt dodaje tylko filtr).

## Skąd są dane

| Co | Źródło |
|---|---|
| Lista sesji, porządek obrad, projekty uchwał | BIP UM Gdyni (publiczne API `api.um.gdynia.pl`, z którego korzysta strona BIP) |
| Podjęte uchwały i ich treść (PDF z uzasadnieniem) | wyszukiwarka uchwał BIP (`/contents/search_ordinances`) |
| Głosowania imienne | PDF „głosowanie” przy każdej uchwale w BIP, wygenerowany przez eSesję |
| Radni, funkcje, kluby | BIP: „Radni IX kadencji”, „Kluby radnych” |

**gdynia.esesja.pl nie jest używana.** Każdy jej adres (nawet `robots.txt`)
zwraca blokadę anty-botową Cloudflare. Operator eSesji napisał, że wprowadził
ją przeciw masowemu automatycznemu pobieraniu. Nie obchodzimy tej blokady.
Szczegóły rozpoznania: [`docs/01-rozpoznanie.md`](docs/01-rozpoznanie.md).

**Ograniczenie:** BIP publikuje głosowanie tylko przy podjętej uchwale. Nie ma
tu głosowań nad poprawkami, projektami odrzuconymi ani spraw proceduralnych.
Strona wypisuje projekty z porządku obrad, przy których w BIP nie ma uchwały.

## Jak to działa

```
BIP API ──> fetch.py (1 zapytanie/s, cache surowych odpowiedzi w cache/raw)
        ──> bip_gdynia.py (sesja, porządek, uchwały, radni, kluby)
        ──> votes.py (parser PDF eSesji) + names.py (nazwiska bez zgadywania)
        ──> checks.py (twarde sprawdzenia) ──> data/gdynia/sesje/<data>_<nr>.json
data/gdynia/opisy + co-dla-mnie ──> descriptions.py (sprawdzenie cytatów) ──> site.py ──> site/
```

| Katalog / plik | Zawartość |
|---|---|
| `corobiwladza/` | kod (tylko biblioteka standardowa Pythona) |
| `data/miasta/gdynia.json` | konfiguracja miasta: identyfikatory kategorii BIP, ustawowy skład, ręczna tabela aliasów nazwisk |
| `data/gdynia/sesje/` | wynik pobrania: JSON z sesją, uchwałami, głosowaniami (nazwiska z PDF i identyfikatory radnych), SHA-256 każdego pliku źródłowego |
| `data/gdynia/opisy/` | opisy „po ludzku” z cytatami |
| `data/gdynia/co-dla-mnie/` | stawki i przykłady dla uchwały podatkowej |
| `site/` | wygenerowana strona (do podglądu; nie jest nigdzie wdrożona) |
| `tests/` | testy (`unittest`) |
| `cache/` | surowe odpowiedzi serwerów, poza gitem (~220 MB) |

### Twarde sprawdzenia (krok 3)

Bez AI i bez heurystyk. Każde z nich ma test, który psuje dane i oczekuje błędu:

- sumy w nagłówku PDF = liczby w nagłówkach sekcji = liczba nazwisk w sekcji,
- suma głosów i nieobecnych = liczba radnych; lista radnych = ustawowy skład (28),
- każde nazwisko jest na liście radnych BIP: dokładnie (kolejność członów
  i myślniki bez znaczenia) albo przez wpis w ręcznej tabeli aliasów;
  jedna różna litera = błąd,
- każdy radny dokładnie raz w każdym głosowaniu; każdy radny w dokładnie
  jednym klubie (albo wśród niezrzeszonych); link przy nazwisku na stronie
  klubów prowadzi do tego samego profilu,
- data uchwały = data głosowania = data sesji; numer sesji i rok w numerze
  uchwały; PDF wygenerowany nie przed głosowaniem; wpis w BIP nie przed sesją,
- numeracja uchwał sesji bez luk; dokładnie 1 PDF głosowania na uchwałę,
  różne pliki i identyfikatory eSesji,
- warunki konieczne podjęcia uchwały (art. 14 ustawy o samorządzie gminnym):
  ZA > PRZECIW oraz obecna co najmniej połowa ustawowego składu
  (obecni = wszyscy – „nieobecni” z PDF).

### Opisy „po ludzku” (krok 4)

1–2 zdania na uchwałę, tylko na podstawie treści uchwały i uzasadnienia.
Szkice napisał model językowy Claude w sesji 12.11.2026. **Przed publikacją
redakcja powinna je przeczytać.** Program pilnuje, żeby:

- każde zdanie miało cytaty i każdy cytat był dosłownie w tekście PDF uchwały,
- opis miał 1–2 zdania i nie zawierał słów oceniających z listy
  (`STOP_WORDS` w `descriptions.py`),
- uchwała bez treści w BIP (12 skarg i petycji) dostała „brak opisu”.

### „A co dla mnie?” (krok 5)

Uchwała XXXVI/902/26 o stawkach podatku od nieruchomości (od 1.01.2027),
porównana z uchwałą XXIII/558/25 (stawki na 2026). Trzy grupy: właściciel
mieszkania, właściciel domu z ogrodem, osoba prowadząca firmę w lokalu.
(Proponowane grupy „rodzic” i „kierowca” nie płacą tego podatku jako takie,
więc wybrałem grupy, których ta uchwała dotyczy.) Każda stawka to cytat
sprawdzany w PDF, a przykłady to wyłącznie powierzchnia × stawka. Fakt
z projektu (1,29 zł za m² mieszkania przed poprawką) pochodzi z PDF projektu
w porządku obrad.

## Koszt jednej sesji

Zmierzone dla XXXVI sesji:

| | |
|---|---|
| Zapytania do sieci | **80**: 4 lista sesji (kategoria kadencji + 3 lata), 1 porządek obrad, 1 lista uchwał, 2 radni i kluby, 42 PDF głosowań, 30 PDF treści. Do tego 3 dla „A co dla mnie?” |
| Czas pobierania | ok. **3,5 min** (limit 1 zapytanie/s plus pobieranie dużych PDF: plan miejscowy 26 MB, aglomeracja 43 MB) |
| Dane | ok. **218 MB** w cache, z czego JSON wynikowy 0,2 MB |
| Ponowne zbudowanie z cache | 0 zapytań, ok. 2 s |

## Drugie miasto z eSesji

Parser PDF „Wyniki głosowania” (`votes.py`) jest wspólny dla wszystkich miast,
które publikują PDF wygenerowane przez app.esesja.pl. Do zmiany:

1. **Adapter BIP.** Każde miasto ma inny system BIP. `bip_gdynia.py` działa
   tylko z API BIP Gdyni. Dla nowego miasta trzeba napisać adapter z tymi
   samymi metodami (`session_posts`, `session`, `resolutions_on`,
   `councillors`, `clubs`).
2. **Plik `data/miasta/<miasto>.json`:** ustawowy skład rady, identyfikatory
   stron BIP, tabela aliasów nazwisk (sprawdzona ręcznie).
3. **Wzorce tytułów** sesji i uchwał (np. „Rady Miasta Gdyni” w wyrażeniach
   regularnych w `bip_gdynia.py`) trzeba przenieść do konfiguracji.
4. Jeśli miasto publikuje głosowania tylko w portalu eSesji, potrzebna jest
   zgoda lub dostęp od operatora eSesji, bo portale są za blokadą anty-botową.

## Licencja

| Co | Licencja | Plik |
|---|---|---|
| Kod (`corobiwladza/`, `tests/`) | **EUPL-1.2** (European Union Public Licence) | [`LICENSE`](LICENSE) |
| Dane i teksty projektu (`data/`, opisy „po ludzku”, „A co dla mnie?”, wygenerowana strona `site/`) | **CC BY 4.0** (Creative Commons Uznanie autorstwa 4.0) | [`LICENSES/CC-BY-4.0.txt`](LICENSES/CC-BY-4.0.txt) |

Przy ponownym użyciu danych lub opisów podaj źródło: **Co robi władza?
(corobiwladza.pl)**.

EUPL-1.2 ma równorzędne oficjalne wersje we wszystkich językach UE, także
po polsku: https://joinup.ec.europa.eu/page/eupl-text-11-12.
W repozytorium jest wersja angielska (tekst z listy SPDX).

Dokumenty źródłowe (uchwały, ich projekty, PDF z wynikami głosowań)
pochodzą z BIP Urzędu Miasta Gdyni. Uchwały i ich projekty nie podlegają
prawu autorskiemu (art. 4 ustawy o prawie autorskim i prawach pokrewnych),
więc licencje projektu ich nie obejmują.
