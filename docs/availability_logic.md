# Rental Availability Logic

## Overview

The TL Rental Manager uses a **fleet capacity-based availability system** with **optimistic booking**.
This allows unlimited reservations while ensuring hard commitments don't exceed actual inventory.

## Key Concepts

### Fleet Capacity
- **Definition:** Total units owned for rental, regardless of current physical location
- **Field:** `product.template.tlrm_fleet_capacity` (computed)
- **Source:** Auto-computed from `stock.quant` quantities across all internal locations in the company
- **Purpose:** Provides a stable base for availability calculations even when items are out on rental
- **Note:** When you add inventory in any warehouse, fleet capacity automatically updates

### Planning vs Physical Commitment
- **Reserved state:** Blocks availability for planning - prevents double-booking, but no stock movements
- **Booked state:** Hard lock with stock movements - creates outbound and return pickings
- **Benefit:** Reserved enables planning without physical inventory changes; Booked commits the physical items

## State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BOOKING STATE MACHINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DRAFT ──► PLANNED ──► RESERVED ──► ONGOING ──► FINISHED ──► RETURNED       │
│    │          │           │           │           │            │             │
│    ▼          ▼           ▼           ▼           ▼            ▼             │
│                                                                              │
│  Planning   Blocks     Hard lock    Out on     Past end    Complete         │
│  No impact  availab.   (picking     rental     date, not   Stock            │
│             for plan   created)     (physical) yet back    returned         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

| State | Blocks Availability? | Picking Status | Can Cancel? |
|-------|---------------------|----------------|-------------|
| draft | No | None | Yes |
| planned | **Yes** (planning) | None | Yes |
| reserved | **Yes** (physical) | Outbound + Return created | Yes (releases stock) |
| ongoing | **Yes** | Outbound done | No |
| finished | **Yes** | Return ready | No |
| returned | No | Return done | N/A |

## Availability Formula

```
available_for_period(product, warehouse, start, end) = 
    fleet_capacity
    - SUM(planned lines overlapping period)
    - SUM(reserved lines overlapping period)
    - SUM(ongoing lines overlapping period)
    - SUM(finished lines overlapping period)
    + SUM(incoming returns before period starts)
```

### Visual Breakdown

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AVAILABILITY CALCULATION                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Fleet Capacity (e.g., 10 projectors)                                       │
│   ════════════════════════════════════════════════════                      │
│                                                                              │
│   [--- planned ---][--- reserved ---][----- ongoing -----][-finished-]      │
│                                                                              │
│   [+ incoming returns to this warehouse before period]                       │
│                                                                              │
│   ═══════════════════════════════════════════════════                       │
│   [                    AVAILABLE                      ]                      │
│                                                                              │
│   Note: All states except 'draft' and 'returned' reduce availability        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cross-Warehouse Returns

Items can return to a different warehouse than they were rented from.

### Line-Level Fields
- `source_warehouse_id`: Where items are rented FROM
- `return_warehouse_id`: Where items return TO (default = source)
- `expected_return_date`: When items are expected back (default = booking.date_end)

### Example: Cross-Warehouse Return

```
Booking: "Event Stockholm Jan 15-20"
├── Line 1: 5 Projectors from Stockholm → return to Stockholm
├── Line 2: 3 Projectors from Stockholm → return to Gothenburg (CUSTOM)
└── Line 3: 2 Speakers from Stockholm → return to Stockholm

Creates pickings:
- 1 Outbound: Stockholm → TL Rented Out (all items)
- 2 Returns:
    - TL Rented Out → Stockholm (5 proj + 2 speakers)
    - TL Rented Out → Gothenburg (3 proj)
```

### Availability Impact

When calculating availability for **Gothenburg** for **Jan 25**:

```
Gothenburg fleet: 5 projectors
+ Incoming from Stockholm booking: 3 (arriving ~Jan 20)
= Available for Jan 25: 8 projectors
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
│  STATE: reserved (SOFT HOLD)                                               │
│  ───────────────────────────                                               │
│  • No picking created yet                                                  │
│  • No stock impact                                                         │
│  • NOT counted in availability (optimistic mode)                           │
│  • Can be overbooked - sales flexibility                                   │
│                                                                            │
│         │ action_book() - HARD AVAILABILITY CHECK HERE                     │
│         ▼                                                                  │
│                                                                            │
│  STATE: booked (HARD LOCK)                                                 │
│  ─────────────────────────                                                 │
│  • Outbound picking created (Warehouse → TL Rental Out)                    │
│  • Return picking(s) created (grouped by destination + date)               │
│  • COUNTED in availability - blocks other bookings                         │
│                                                                            │
│         │ action_mark_ongoing() - outbound picking validated               │
│         ▼                                                                  │
│                                                                            │
│  STATE: ongoing                                                            │
│  ───────────────                                                           │
│  • Stock physically moved to "TL Rental Out" location                      │
│  • COUNTED in availability                                                 │
│                                                                            │
│         │ action_finish()                                                  │
│         ▼                                                                  │
│                                                                            │
│  STATE: finished                                                           │
│  ───────────────                                                           │
│  • Past return date, waiting for physical return                           │
│  • COUNTED in availability                                                 │
│                                                                            │
│         │ action_return() - return picking validated                       │
│         ▼                                                                  │
│                                                                            │
│  STATE: returned                                                           │
│  ────────────────                                                          │
│  • Stock moved back to return warehouse                                    │
│  • NOT counted - items available again                                     │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Example Scenario

```
Product: Projector
Fleet Capacity: 10 units

┌─────────────────────────────────────────────────────────────────────────────┐
│ Timeline                                                                    │
│                                                                             │
│     Jan 1        Jan 15       Feb 1        Feb 15       Mar 1              │
│       │            │            │            │            │                 │
│       ├────────────┼────────────┼────────────┼────────────┤                 │
│       │            │            │            │            │                 │
│       │  Booking A: 5 units (BOOKED - hard lock)         │                 │
│       │  ════════════════════════                        │                 │
│       │            │            │            │            │                 │
│       │            │  Booking B: 3 units (RESERVED - soft hold)            │
│       │            │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │                 │
│       │            │            │            │            │                 │
└─────────────────────────────────────────────────────────────────────────────┘

Availability calculation (optimistic mode):

• Jan 1-14:   10 - 5 (booked) = 5 available
• Jan 15-31:  10 - 5 (booked) = 5 available  (reserved B doesn't block!)
• Feb 1-14:   10 - 0 = 10 available
• Feb 15+:    10 - 0 = 10 available

When Booking B tries to LOCK (reserved → booked):
• System checks: 10 - 5 = 5 available, requesting 3 → OK, can lock
```

## Key Design Decisions

| Aspect | Our Approach | Why |
|--------|--------------|-----|
| Base capacity | `tlrm_fleet_capacity` | Stable base regardless of physical location |
| Soft hold | `reserved` state | Sales flexibility, allows overbooking |
| Hard lock | `booked` state | Operations confirms real availability |
| What blocks | `booked`, `ongoing`, `finished` | Only committed items block |
| Cross-warehouse | Per-line `return_warehouse_id` | Supports complex logistics |
| Incoming returns | Counted in availability | Future availability projection |
| Odoo stock.move | Physical transfer only | Not for availability planning |
