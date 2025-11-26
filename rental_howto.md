# Rental How-To (stock_rental_manager)

Det här dokumentet beskriver **hur** man arbetar praktiskt med uthyrning i Odoo med modulen `stock_rental_manager`.

Målbilden är:

- Alla lagersatta produkter kan hyras.
- Lagerkapacitet tas direkt från Odoo-lagret.
- Uthyrningar kopplas alltid till ett **projekt**.
- Lagerpersonalen styr **när** uthyrningen startar och avslutas genom att validera plockningar (stock pickings).
- En bokning kan plockas från **flera warehouses** samtidigt.

---

## 1. Förutsättningar

- Modulen `stock_rental_manager` är installerad.
- Ett eller flera **source warehouses** (ordinarie lager) är konfigurerade.
- Ett eller flera **rental warehouses** (lager som representerar "ute på uthyrning") är konfigurerade.
- Produkter som ska hyras är vanliga storable produkter i Odoo.

---

## 2. Skapa en rental booking

1. Gå till menyn:
   - *Inventory / Lager* → **Rental → Bookings**.
2. Klicka på **Create**.
3. Fyll i header-fält:
   - **Project** – projektet som uthyrningen hör till (obligatoriskt).
   - **Source Warehouse** – standardkälla för raderna (kan justeras per rad senare).
   - **Rental Warehouse** – standard-rental-warehouse för raderna.
   - **Start Date / End Date** – planerat datumintervall för uthyrningen.
4. Lägg till rader på fliken **Lines**:
   - Välj **Product**.
   - Välj **Source Warehouse** (om du vill avvika från headerns standard).
   - Välj **Rental Warehouse** (om du vill avvika från headerns standard).
   - Ange **Quantity**.

### 2.1 Availability-kontroll

När du sparar och bekräftar bokningen (se nästa steg) så gör systemet en availability-kontroll per rad:

- För varje rad räknas:
  - Lagerkapacitet i valt **source warehouse** för produkten (via `stock.quant`).
  - Hur mycket som redan är bokat/uthyrt för samma produkt, samma warehouse och överlappande datum.
- Om `requested > available` får du ett felmeddelande och får justera bokningen.

---

## 3. Bekräfta en booking (skapa plockningar)

När alla fält och rader är ifyllda:

1. Klicka på **Confirm** medan bokningen är i state `Draft`.
2. Systemet gör då:
   - Validerar datum, projekt och att alla rader har produkt + source/rental warehouse.
   - Kör availability-kontrollen på varje rad.
   - **Skapar en eller flera stock pickings**:
     - Raderna grupperas per `(Source Warehouse, Rental Warehouse)`.
     - För varje grupp skapas en plockning:
       - Från: `Source Warehouse` (lot stock location).
       - Till: `Rental Warehouse` (lot stock location).
       - Typ: intern plockning (warehouse `int_type_id`).
       - Origin: bookingens namn.
       - Kopplad till bokningen via specialfält.
   - Sätter bookingens state till **`Reserved`**.

> Viktigt: Efter Confirm är inga varor ännu "ute" – de är bara **reserverade** via plockningarna.

---

## 4. Lagerpersonalen plockar och startar uthyrningen

Lagerpersonalen arbetar huvudsakligen i plockningsvyerna (Inventory / Lager → Operations → Transfers).

För att starta en uthyrning:

1. Leta upp de plockningar som har **Origin = bookingens namn**.
2. Öppna en plockning.
3. Plocka fysiskt de produkter som står på plockningen.
4. Justera ev. plockade kvantiteter om något avviker.
5. Klicka på **Validate** för att markera plockningen som `Done`.

När plockningen valideras:

- Kvantiteten flyttas i lagret från `Source Warehouse` till `Rental Warehouse`.
- Om plockningen är märkt som **Rental Out** (vilket den är för startplockningar):
  - och bokningen är i state `Reserved`,
  - så sätts bokningen automatiskt till state **`Ongoing`**.

Du kan följa statusen på bokningen i rental-booking-formuläret (statusfältet i headern).

---

## 5. Avsluta uthyrningen och hantera retur

När utrustningen kommer tillbaka:

1. Öppna rental-bokningen.
2. Klicka på **Return**.
3. Systemet skapar då **return-pickings**:
   - En eller flera plockningar per `(Source Warehouse, Rental Warehouse)`.
   - Från: `Rental Warehouse`.
   - Till: motsvarande `Source Warehouse`.
   - Origin: bookingens namn.
4. Lagerpersonalen går till retur-plockningarna, plockar fysiskt tillbaka utrustningen och klickar på **Validate**.

När en retur-plockning valideras:

- Kvantiteten flyttas från `Rental Warehouse` till `Source Warehouse` i lagret.
- Bokningens state sätts till **`Returned`**.

Du kan därefter ev. sätta bokningen till `Finished` manuellt om du vill markera att den är helt administrativt klar.

---

## 6. Multi-warehouse-scenarier

Eftersom varje rad har egna `Source Warehouse` och `Rental Warehouse` kan du:

- Ha en enda booking för ett projekt.
- Plocka vissa produkter från Warehouse A och andra från Warehouse B.
- Ha olika rental-warehouses om du vill (t.ex. olika geografiska områden).

Systemet:

- Validerar availability per rad och warehouse.
- Skapar en separat picking per `(Source Warehouse, Rental Warehouse)`-kombination.

Detta innebär att:

- Lagerpersonalen kan arbeta precis som med vanliga plockningar, men de är tydligt taggade till en rental booking.
- Projektledaren ser allt som en sammanhållen booking mot projektet.

---

## 7. Varningar via cron

Ett schemalagt jobb (cron) skickar automatiskt meddelanden på bokningen:

- Om en booking är `Reserved` och nuet passerar **Start Date**:
  - Meddelande: att bokningen borde starta.
- Om en booking är `Reserved` eller `Ongoing` och nuet passerar **End Date**:
  - Meddelande: att bokningen borde avslutas/returneras.

Cron **ändrar inte längre state** – den är bara en påminnelse till användare.

---

## 8. Produktfliken "Bookings" (översikt)

På produktformuläret finns en flik **Bookings** som ger överblick:

- **Configuration**
  - Minsta uthyrningstid i timmar/dagar/veckor.
- **Pricing**
  - Pris per timme/dag/vecka.
- **Availability**
  - `rental_status` – sammanfattning (Available / Reserved / Rented / Unavailable).
  - `rental_available_units` – global tillgänglighet (alla interna lager) minus bokade/uthyrda enheter.
  - `rental_reserved_units` – hur mycket som är bokat framåt.
  - `rental_rented_units` – hur mycket som är ute nu.

Denna flik är **översiktlig**, medan själva besluten kring tillgänglighet per datum och warehouse hanteras i bokningen.

---

## 9. Sammanfattning av arbetsflöde

1. Skapa booking (projekt, datum, rader med produkter och warehouses).
2. Confirm → availability-check + plockningar skapas → booking = `Reserved`.
3. Lager plockar och validerar outbound-pickings → booking = `Ongoing`.
4. När utrustningen kommer tillbaka: booking **Return** → retur-pickings.
5. Lager validerar retur-pickings → booking = `Returned`.
6. Cron skickar bara varningar när datum passerats, ändrar inte state.
