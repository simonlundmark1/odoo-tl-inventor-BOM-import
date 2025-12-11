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

## 8. OWL-komponenter och QWeb-templates

- För OWL-baserade backend-komponenter (client actions, views) gäller:
  - QWeb-templates som används av OWL **måste** ligga under `static/src/xml/`.
  - XML-filen måste dessutom registreras i `web.assets_backend` i `__manifest__.py`, t.ex.:
    - `"tl_rental_manager/static/src/xml/rental_availability_templates.xml"`.
- Om templatet bara ligger i `views/*.xml` och inte i `static/src/xml` + assets kommer OWL att kasta:
  - `OwlError: Missing template: "<t-name>" (for component "<ComponentName>")`.
- Mönster i den här modulen:
  - JS-klasser i `static/src/js/` (`@odoo-module`).
  - Tillhörande OWL-templates i `static/src/xml/*.xml` med samma `t-name` som anges på komponenten.

## 9. `res.groups` – `category_id` borttaget

- I Odoo 19 har fältet `category_id` **tagits bort** från modellen `res.groups`.
- Försök att definiera grupper med `<field name="category_id" ref="..."/>` ger felet:
  - `ValueError: Invalid field 'category_id' in 'res.groups'`.
- Tidigare versioner (≤18) använde `category_id` för att gruppera säkerhetsgrupper under modulkategorier i användargränssnittet.
- **Lösning i Odoo 19:**
  - Ta bort `category_id`-fältet helt från XML-definitionen av `res.groups`.
  - Grupper definieras nu enbart med `name` och eventuellt `implied_ids`.
- Exempel på korrekt gruppdefinition i Odoo 19:
  ```xml
  <record id="tlrm_group_user" model="res.groups">
      <field name="name">TL Rental User</field>
      <field name="implied_ids" eval="[(4, ref('base.group_user'))]"/>
  </record>
  ```
- **OBS:** `ir.module.category` finns fortfarande, men kopplingen till `res.groups` via `category_id` är borta.

## 10. JavaScript RPC – `rpc` service borttaget

- I Odoo 19 har **`rpc` service tagits bort** från OWL-komponenter.
- Försök att använda `useService("rpc")` ger felet:
  - `Error: Service rpc is not available`.
- **Lösning i Odoo 19:**
  - Importera `jsonrpc` direkt från `@web/core/network/rpc`.
  - Använd `jsonrpc()` som en vanlig funktion istället för en service.
- Exempel på korrekt användning:
  ```javascript
  /** @odoo-module **/
  import { jsonrpc } from "@web/core/network/rpc";
  
  // I en async metod:
  async loadData() {
      const result = await jsonrpc('/my/controller/endpoint', {
          param1: value1,
          param2: value2,
      });
  }
  ```
## 11. stock.move – `name` fält borttaget

- I Odoo 19 har **`name` fältet tagits bort** från `stock.move`.
- Försök att skapa en move med `'name': ...` ger felet:
  - `ValueError: Invalid field 'name' in 'stock.move'`
- **Lösning:** Ta bort `name` från move-skapande kod. Odoo genererar automatiskt en beskrivning.

```python
# Felaktigt (fungerar INTE i Odoo 19):
move_vals = {
    'name': product.display_name,  # <-- TA BORT
    'product_id': product.id,
    ...
}

# Korrekt (Odoo 19):
move_vals = {
    'product_id': product.id,
    ...
}
```

---

- **Felaktigt (fungerar INTE i Odoo 19):**
  ```javascript
  // FUNGERAR INTE:
  this.rpc = useService("rpc");
  const result = await this.rpc('/my/endpoint', {});
  ```
- **Korrekt (Odoo 19):**
  ```javascript
  import { jsonrpc } from "@web/core/network/rpc";
  const result = await jsonrpc('/my/endpoint', {});
  ```
- **OBS:** `orm` service (`useService("orm")`) fungerar fortfarande för att anropa modellmetoder via `this.orm.call()`.

## 11. JavaScript-mönster för Odoo 19 OWL-komponenter

Komplett exempel på en OWL-komponent i Odoo 19:

```javascript
/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { jsonrpc } from "@web/core/network/rpc";

export class MyComponent extends Component {
    static template = "my_module.MyComponentTemplate";
    static props = { "*": true };

    setup() {
        // Tillgängliga services i Odoo 19:
        this.orm = useService("orm");           // För modell-anrop
        this.action = useService("action");     // För att öppna actions
        this.notification = useService("notification"); // För notifieringar
        // OBS: useService("rpc") finns INTE längre!
        
        this.state = useState({
            loading: true,
            data: null,
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        // Anropa modellmetod via orm:
        const records = await this.orm.call(
            "my.model",
            "my_method",
            [arg1, arg2],
            { kwarg1: value1 }
        );

        // Anropa controller-endpoint via jsonrpc:
        const result = await jsonrpc('/my/controller/endpoint', {
            param1: value1,
        });

        this.state.data = result;
        this.state.loading = false;
    }
}

registry.category("actions").add("my_action_tag", MyComponent);
```
