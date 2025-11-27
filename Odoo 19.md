# Odoo 19 – Tekniska noter och nya regler

## 1. `read_group` är deprecated

- Sedan Odoo 19.0 finns en varning:
  - `DeprecationWarning: Since 19.0, read_group is deprecated. Please use _read_group in the backend code or formatted_read_group for a complete formatted result`.
- Konsekvens för egen kod:
  - Befintligt `read_group` fungerar fortfarande men ger varningar i loggen.
  - Ny kod bör skriva om till `_read_group` eller `formatted_read_group` när möjligt.

## 2. Postgres-versionkrav

- Loggar visar:
  - `UserWarning: Postgres version is 120004, lower than minimum required 130000`.
- Odoo 19 förväntar sig minst PostgreSQL 13.
- Lägre versioner fungerar, men ger varningar och är inte officiellt supportade.

## 3. `read_group` resultatstruktur

- I Odoo 19 (och senare 14+) returnerar `read_group` fält med **ursprungligt fältnamn** även när man anger `':sum'` i argumentet.
  - Exempel-anrop:
    - `Quant.read_group(domain, ['quantity:sum', 'reserved_quantity:sum'], [])`
  - Exempel-resultat (utdrag från loggar):
    - `{'__count': 1, 'quantity': 10.0, 'reserved_quantity': 0.0, '__domain': [...]}`
- Viktigt:
  - Nycklarna är `quantity` och `reserved_quantity`, **inte** `quantity_sum` eller `reserved_quantity_sum`.
  - Felaktig användning av `quantity_sum` ger alltid 0 (eller `None`) och leder till att beräkningar som lagerkapacitet blir 0 trots att det finns lager.

## 4. Global lagerkapacitet per bolag

- I den här modulen beräknas tillgänglighet för uthyrning globalt per bolag:
  - Domän mot `stock.quant`:
    - `('product_id', '=', product.id)`
    - `('company_id', '=', company.id)`
    - `('location_id.usage', '=', 'internal')`
- Detta innebär:
  - Tillgänglig kapacitet bygger på **allt internt lager** inom bolaget, oberoende av specifikt warehouse.
  - Detta kan skilja sig från standard Odoo-logik om man normalt filtrerar per warehouse/location.

## 5. Skillnad mellan "On Hand" och uthyrningskontrollen

- `On Hand` i Odoo:
  - Visar globalt lager för produkten över alla interna locations.
- Uthyrningskontrollen i modulen:
  - Räknar också globalt (i nuvarande version), men kräver att `read_group` läses korrekt (se punkt 3).

## 6. Rekommendationer vid utveckling mot Odoo 19

- Kontrollera alltid i loggarna vilka nycklar `read_group` faktiskt returnerar.
- Var beredd på deprecations (som `read_group`) och planera migration till nya API:n (`_read_group`/`formatted_read_group`).
- Se till att Postgres-versionen på sikt uppgraderas till minst 13 för att slippa varningar och få officiellt stöd.

## 7. `stock.move` och fältet `name`

- I den här Odoo 19-byggnaden accepterar modellen `stock.move` **inte** ett fält `name` vid `create`.
- Försök att göra `Move.create({'name': ...})` ger felet:
  - `ValueError: Invalid field 'name' in 'stock.move'`.
- Rekommenderat arbetssätt:
  - Skicka bara standardfält: `product_id`, `product_uom`, `product_uom_qty`, `picking_id`, `company_id`, `location_id`, `location_dest_id`, osv.
  - Låt Odoo själv hantera visningsnamn (`display_name`) baserat på produkt och plockning.
