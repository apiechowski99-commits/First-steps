# Krok 1: rozpoznanie źródeł (Rada Miasta Gdyni)

Stan na: 12.11.2026. Wszystkie zapytania szły z identyfikatorem
`JakiStan-prototyp/0.1 (badanie, niekomercyjne)`, z odstępem ≥ 1 s
(wyjątek: 4 wczytania BIP w przeglądarce bez interfejsu, opisane niżej).

## 1. Ostatnia sesja

**XXXVI sesja Rady Miasta Gdyni, 28 października 2026 r.**

- Porządek obrad (BIP):
  https://bip.um.gdynia.pl/rok-2026-4,9408/xxxvi-sesja-rady-miasta-gdyni-z-28-pazdziernika-2026-r,626304
- Następna sesja: 25 listopada 2026 r. (źródło: artykuł gdynia.pl, tylko kontekst).

Co mówią dane z BIP:

| Element | Liczba | Źródło |
|---|---|---|
| Projekty uchwał w porządku obrad | 28 + 3 z aneksu = 31 | post BIP 626304 |
| Uchwały podjęte z datą 28.10.2026 | 42 (nr XXXVI/899/26 – XXXVI/940/26) | wyszukiwarka uchwał BIP |
| ...w tym z treścią uchwały (PDF) | 30 | jw. |
| ...w tym tylko z PDF „głosowanie" (skargi, petycje: nr 928–939) | 12 | jw. |
| Projekty z porządku bez podjętej uchwały | 2 (pkt 5.3 pożyczka długoterminowa, pkt 5.5 InnoBaltica) | porównanie porządku i wyszukiwarki |

Uchwały nr 928–940 (skargi, petycje, komisja doraźna) nie były w
opublikowanym porządku obrad. Dla punktów 5.3 i 5.5 BIP nie mówi, co się
stało (zdjęcie z porządku, odrzucenie?). Tę informację ma eSesja albo
protokół sesji, który zostanie przyjęty na następnej sesji.

## 2. Źródła i ich struktura

### 2a. gdynia.esesja.pl: zablokowane dla programów

- **Każdy adres** (`/`, `/wcag/`, `/wcag/posiedzenia.asp`, nawet `/robots.txt`)
  zwraca `HTTP 403` z nagłówkiem `cf-mitigated: challenge`, czyli wyzwanie
  anty-botowe Cloudflare („Just a moment...”, wymaga JavaScriptu i ciasteczek).
- Operator systemu napisał 5.10.2026, że wdrożył Cloudflare WAF, żeby
  ograniczyć „masowe, automatyczne pobieranie” projektów uchwał i protokołów,
  m.in. na potrzeby systemów AI:
  https://esesja.pl/aktualnosci/505/esesja-wzmacnia-ochrone-przed-automatycznym-ruchem-i-cyberzagrozeniami.htm
- `esesja.pl/robots.txt` blokuje `/zalaczniki/` i `*.pdf`.
- Nie znalazłem regulaminu portalu mieszkańca eSesji.

**Wniosek:** nie obchodzę tej blokady (np. przeglądarką udającą człowieka).
Operator wprost nie chce ruchu automatycznego. Struktury stron
`posiedzenie.asp` / `glosowanie.asp` / `radny/` nie mogłem więc sprawdzić.

### 2b. bip.um.gdynia.pl: otwarte, z publicznym API JSON

Strona BIP to aplikacja JavaScript (React). Dane pobiera z publicznego API:
`https://api.um.gdynia.pl` (adres podany w `https://bip.um.gdynia.pl/js/config.js`).
Przeglądarka nie jest potrzebna, wystarczą zwykłe zapytania o JSON.
`bip.um.gdynia.pl/robots.txt`: `Disallow:` puste, czyli wszystko dozwolone.
`api.um.gdynia.pl/robots.txt`: brak pliku (404). API nie stoi za Cloudflare.

Uwaga o rozpoznaniu: 4 wczytania BIP w przeglądarce bez interfejsu
(Playwright) wysłały po ~30 zapytań naraz, tak jak zwykły odwiedzający.
Program pobierający nie będzie używał przeglądarki, tylko API, po 1 zapytaniu
na sekundę.

| Do czego | Zapytanie |
|---|---|
| Lista sesji 2026 | `GET /contents/posts/category/9408?limit=100&basic=1` |
| Porządek obrad + linki do projektów | `GET /contents/posts/{id}` (pole `content`, HTML) |
| Uchwały z danego dnia | `GET /contents/search_ordinances?form={"number":"","date":"28.10.2026","category":""}` |
| Lista radnych IX kadencji (28 osób) | `GET /contents/posts/category/9175?limit=100&basic=1` |
| Kluby radnych | `GET /contents/posts/601379` |
| Profil radnego | `GET /contents/posts/{id}` (pole `extended_data`) |

Każda uchwała z wyszukiwarki ma:
- tytuł z numerem, datą i przedmiotem („w sprawie...”),
- załączniki na `legacy.um.gdynia.pl`:
  - **treść uchwały** (PDF z systemu Legislator, z warstwą tekstową,
    **uzasadnienie na końcu**),
  - **„głosowanie”**: PDF wygenerowany przez `app.esesja.pl` z warstwą tekstową.
- metadane: osoba odpowiedzialna, data wytworzenia i publikacji, historia zmian.

Projekty uchwał (wersje przed poprawkami) leżą na `static.um.gdynia.pl`
i są linkowane z porządku obrad.

### 2c. PDF „głosowanie”: to, czego szukaliśmy w eSesji

Przykład: uchwała XXXVI/902/26 (podatek od nieruchomości), PDF
`wyniki_glosowania_1968059`:

```
Głosowano w sprawie: projekt uchwały w sprawie określenia wysokości stawek
podatku od nieruchomości na terenie Miasta Gdyni
ZA: 27, PRZECIW: 0, WSTRZYMUJĘ SIĘ: 0, BRAK GŁOSU: 0, NIEOBECNI: 1
Wyniki imienne:
ZA (27)  Norbert Anisowicz, Dominik Aziewicz, ...
PRZECIW (0) / WSTRZYMUJĘ SIĘ (0) / BRAK GŁOSU (0)
NIEOBECNI (1)  Anna Salomon
Głosowanie z dnia: 28.10.2026, 13:26:04
```

Sumy i nazwiska są w jednym dokumencie, więc da się je twardo sprawdzić
(krok 3). Liczba w tytule PDF (1968059) to najpewniej identyfikator
głosowania w eSesji.

**Ograniczenie:** BIP publikuje głosowanie **tylko nad podjętą uchwałą**
(głosowanie końcowe). Nie ma w nim:
- głosowań nad poprawkami (np. poprawka do uchwały podatkowej:
  stawka za mieszkanie 1,29 → 1,24 zł/m², opisana w artykule gdynia.pl),
- głosowań nad projektami odrzuconymi lub zdjętymi (pkt 5.3, 5.5),
- głosowań proceduralnych (porządek obrad, protokół).

### 2d. Nazwiska: trzy różne zapisy tej samej osoby

| PDF głosowania | Lista radnych BIP | Kluby radnych BIP |
|---|---|---|
| Marcus da Silva | da Silva de Oliveira Marcus | da Silva de Oliveira Marcus |
| Natalia Kłopotek Główczewska | Kłopotek - Główczewska Natalia | Kłopotek - Główczewska Natalia |
| Mariola Śrubarczyk - Cichowska | Śrubarczyk - Cichowska Mariola | Śrubarczyk-Cichowska Mariola |

PDF ma kolejność „imię nazwisko”, BIP „nazwisko imię”. Nazwiska w PDF
łamią się między wierszami. Potrzebna jest jawna tabela aliasów
(plik w repo, ręcznie sprawdzona). Nazwisko spoza tabeli to błąd.

### 2e. Kluby (stan strony BIP z 17.09.2026)

| Klub | Liczba radnych |
|---|---|
| Gdynia Niezależna | 5 |
| Koalicja Obywatelska, Ruchy Miejskie i Lewica | 13 |
| Samorządność | 5 |
| Radni niezrzeszeni | 5 |
| **Razem** | **28** (zgadza się z listą radnych i sumą w PDF: 27 + 1) |

### 2f. gdynia.pl: tylko kontekst

- `robots.txt` blokuje m.in. `/module*`, `/storage`, `/dzielnice`.
  Artykuły w `/mieszkaniec/co-nowego,...` są dozwolone.
- „Za nami XXXVI sesja”:
  https://www.gdynia.pl/mieszkaniec/co-nowego,2774/za-nami-xxxvi-sesja-rady-miasta-gdyni,599367
- Warunki: zdjęcia i grafiki tylko niekomercyjnie, z podaniem źródła.
  Nie kopiujemy treści ani zdjęć, najwyżej linkujemy.

## 3. Prawo i dane osobowe

- Uchwały i ich projekty to akty normatywne i dokumenty urzędowe, więc nie
  podlegają prawu autorskiemu (art. 4 ustawy o prawie autorskim).
- Imienne wykazy głosowań radnych gmina publikuje w BIP z mocy ustawy
  o samorządzie gminnym (art. 14).
- Profile radnych w BIP zawierają też dane prywatne (rok urodzenia,
  wykształcenie, hobby, zdjęcie). **Bierzemy tylko**: imię i nazwisko,
  funkcję w radzie, klub, link do profilu w BIP.
- BIP sam anonimizuje osoby prywatne w tytułach („skargi XX”). Zostawiamy
  to bez zmian.
- Nie znalazłem w BIP Gdyni osobnej strony z warunkami ponownego
  wykorzystywania informacji.

## 4. Koszt pobrania jednej sesji przez BIP (szacunek)

| Krok | Zapytania |
|---|---|
| Lista sesji, porządek obrad | 2 |
| Wyszukiwarka uchwał (1 data) | 1 |
| Radni + kluby | 2 |
| PDF „głosowanie” (42 × ~210 kB = 8,6 MB) | 42 |
| PDF treści uchwał (30 plików, razem ~207 MB; największe to plan miejscowy 26 MB i aglomeracja 43 MB, bo zawierają mapy) | 30 |
| **Razem** | **~77 zapytań, ~1,5 min przy 1 zapytaniu/s, ~216 MB** |

Surowe PDF trzymamy w lokalnym cache (poza gitem, bo są za duże).
W repo zostaje JSON wynikowy z sumami kontrolnymi plików (SHA-256).

## 5. Decyzje do podjęcia przed pisaniem kodu

1. **Źródło głosowań.** Propozycja: tylko BIP (API + PDF „głosowanie”).
   Pomijamy gdynia.esesja.pl, dopóki operator nie da zgody albo dostępu.
   Konsekwencja: prototyp pokazuje głosowania końcowe nad 42 podjętymi
   uchwałami, bez poprawek i bez projektów odrzuconych.
   Uzupełnienie na później: zapytać operatora eSesji o dostęp
   lub eksport albo złożyć wniosek o informację publiczną do Biura Rady
   Miasta o pełny wykaz głosowań sesji.
2. **Publikacja w gicie.** Repo `First-steps` jest **publiczne**. Czy
   wypychać commity na gałąź `claude/jaki-stan-gdynia-prototype-85sqgb`
   na bieżąco, czy traktujesz to jako publikację i mam czekać?
3. **Definicja „sporne/zgodne”** (do kroku 6). Propozycja reguły, takiej
   samej dla wszystkich: „zgodne” = żadnego głosu przeciw ani
   wstrzymującego się; w przeciwnym razie „z głosami przeciw lub
   wstrzymującymi się”. Bez progów procentowych.
