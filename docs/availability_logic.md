# Rental Availability Logic

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ODOO CORE                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         stock.quant                                  │    │
│  │  ┌──────────────────┐    ┌──────────────────┐                       │    │
│  │  │   qty_on_hand    │    │ reserved_quantity│  ← Set by Odoo when   │    │
│  │  │   (physical)     │    │ (Odoo internal)  │    picking.action_    │    │
│  │  │                  │    │                  │    assign() is called │    │
│  │  │  WE USE THIS ✓   │    │  WE IGNORE THIS  │                       │    │
│  │  └──────────────────┘    └──────────────────┘                       │    │
│  │                                                                      │    │
│  │  qty_available = qty_on_hand - reserved_quantity  ← WE DON'T USE    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      stock.picking / stock.move                      │    │
│  │                                                                      │    │
│  │  Created when booking is confirmed. Moves stock between locations.  │    │
│  │  We use this for PHYSICAL movement only, not for availability.      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘

                                    │
                                    │ We read qty_on_hand
                                    ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                         TL RENTAL MANAGER (Custom)                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    AVAILABILITY CALCULATION                          │    │
│  │                                                                      │    │
│  │   ┌─────────────┐     ┌─────────────────────────────────────────┐   │    │
│  │   │ qty_on_hand │  -  │  SUM of booking lines where:            │   │    │
│  │   │ (from Odoo) │     │    • state = 'reserved'                 │   │    │
│  │   │             │     │    • date range overlaps                │   │    │
│  │   │             │     │    • same warehouse                     │   │    │
│  │   └─────────────┘     └─────────────────────────────────────────┘   │    │
│  │         │                              │                             │    │
│  │         └──────────────┬───────────────┘                             │    │
│  │                        ▼                                             │    │
│  │              ┌─────────────────┐                                     │    │
│  │              │    AVAILABLE    │                                     │    │
│  │              │   for period    │                                     │    │
│  │              └─────────────────┘                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    BOOKING LINE STATES                               │    │
│  │                                                                      │    │
│  │   draft ──────► reserved ──────► ongoing ──────► finished ──► returned│   │
│  │     │              │                │                                │    │
│  │     │              │                │                                │    │
│  │     ▼              ▼                ▼                                │    │
│  │  No effect    Blocks future    Stock already                         │    │
│  │  on avail.    availability     moved out                             │    │
│  │               (we count it)    (qty_on_hand                          │    │
│  │                                already reduced)                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## State Transitions & Stock Impact

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│  STATE: draft                                                              │
│  ─────────────                                                             │
│  • No picking created                                                      │
│  • No stock impact                                                         │
│  • NOT counted in availability                                             │
│                                                                            │
│         │ action_confirm()                                                 │
│         ▼                                                                  │
│                                                                            │
│  STATE: reserved                                                           │
│  ────────────────                                                          │
│  • Picking created (Warehouse Stock → TL Rental Out)                       │
│  • Picking assigned (Odoo reserves stock internally)                       │
│  • qty_on_hand: UNCHANGED (stock still in warehouse)                       │
│  • WE COUNT THIS in availability calculation                               │
│                                                                            │
│         │ picking validated (action_done)                                  │
│         ▼                                                                  │
│                                                                            │
│  STATE: ongoing                                                            │
│  ───────────────                                                           │
│  • Stock physically moved to "TL Rental Out" location                      │
│  • qty_on_hand: REDUCED (stock left the warehouse)                         │
│  • NOT counted separately (already reflected in qty_on_hand)               │
│                                                                            │
│         │ date_end passed                                                  │
│         ▼                                                                  │
│                                                                            │
│  STATE: finished                                                           │
│  ───────────────                                                           │
│  • Waiting for return                                                      │
│  • Stock still in "TL Rental Out"                                          │
│  • qty_on_hand: Still reduced                                              │
│                                                                            │
│         │ action_return() + picking validated                              │
│         ▼                                                                  │
│                                                                            │
│  STATE: returned                                                           │
│  ────────────────                                                          │
│  • Stock moved back (TL Rental Out → Warehouse Stock)                      │
│  • qty_on_hand: RESTORED                                                   │
│  • Available for new bookings                                              │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Example Scenario

```
Product: Balk
Warehouse: Stockholm
Physical stock (qty_on_hand): 20 units

┌─────────────────────────────────────────────────────────────────────────────┐
│ Timeline                                                                    │
│                                                                             │
│     Jan 1        Jan 15       Feb 1        Feb 15       Mar 1              │
│       │            │            │            │            │                 │
│       ├────────────┼────────────┼────────────┼────────────┤                 │
│       │            │            │            │            │                 │
│       │  Booking A: 5 units (reserved)       │            │                 │
│       │  ════════════════════════            │            │                 │
│       │            │            │            │            │                 │
│       │            │  Booking B: 3 units (reserved)      │                 │
│       │            │  ═══════════════════════════════════│                 │
│       │            │            │            │            │                 │
└─────────────────────────────────────────────────────────────────────────────┘

Availability calculation for different periods:

• Jan 1-14:   20 - 5 = 15 available
• Jan 15-31:  20 - 5 - 3 = 12 available (both overlap)
• Feb 1-14:   20 - 3 = 17 available (only B overlaps)
• Feb 15+:    20 - 0 = 20 available (no overlaps)
```

## Key Design Decisions

| Aspect | Our Approach | Why |
|--------|--------------|-----|
| Base stock | `qty_on_hand` | Physical count, ignores Odoo's internal reservations |
| Reservation tracking | Booking line state = 'reserved' | Simple, date-aware, no double-counting |
| Ongoing rentals | Not counted separately | `qty_on_hand` already reduced when stock moved |
| Odoo stock.move | Used for physical transfer only | Not for availability planning |
