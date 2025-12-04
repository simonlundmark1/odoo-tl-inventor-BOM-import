# TL Rental Manager

Odoo 19 Community module for managing stockable product rentals with project-based bookings and availability planning.

## Features

- **Rental Bookings**: Create and manage rental bookings linked to projects
- **Availability Grid**: Visual week-by-week availability calendar for all products
- **Stock Integration**: Automatic stock moves when confirming/returning rentals
- **Multi-company Support**: Full multi-company record rules
- **Calendar Integration**: Week numbers tuned for Swedish conventions

## Use Cases

- Rent out physical equipment (tools, machines, vehicles)
- Plan project-specific rentals and check stock availability
- Get a quick overview of booked vs available units per week

## Module Structure

```
tl_rental_manager/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── controllers.py          # JSON-RPC endpoints for availability API
├── data/
│   ├── rental_cron.xml         # Scheduled actions
│   └── rental_sequence.xml     # Booking reference sequence (TLRM/xxxxx)
├── models/
│   ├── __init__.py
│   ├── product.py              # product.template extensions (tlrm_* fields)
│   ├── rental_booking.py       # tl.rental.booking & tl.rental.booking.line
│   └── stock_picking.py        # stock.picking extensions (tlrm_* fields)
├── security/
│   ├── ir.model.access.csv     # Access rights
│   └── rental_security.xml     # Groups and record rules
├── static/
│   └── src/
│       ├── css/
│       │   └── rental_availability.css   # Availability grid styles
│       ├── js/
│       │   ├── booking_availability_action.js   # Booking wizard action handler
│       │   ├── booking_availability_wizard.js   # OWL booking availability wizard
│       │   ├── rental_availability_action.js    # OWL global availability grid
│       │   └── rental_calendar.js               # Calendar view patch
│       └── xml/
│           ├── booking_availability_wizard_templates.xml  # Wizard templates
│           └── rental_availability_templates.xml          # Grid templates
└── views/
    ├── product_view.xml              # Product form extensions
    └── rental_booking_views.xml      # Booking views, menus, actions
```

## Naming Conventions

This module follows Odoo 19 community guidelines with unique prefixes:

| Type | Prefix | Example |
|------|--------|---------|
| Models | `tl.rental.*` | `tl.rental.booking`, `tl.rental.booking.line` |
| Fields on inherited models | `tlrm_` | `tlrm_price_hour`, `tlrm_status`, `tlrm_booking_id` |
| XML IDs | `tlrm_` | `tlrm_action_booking`, `tlrm_view_booking_form` |
| Security groups | `tlrm_group_` | `tlrm_group_user`, `tlrm_group_manager` |
| CSS classes | `o_tlrm_` | `o_tlrm_availability_action`, `o_tlrm_cell_clickable` |
| Client action tags | `tlrm_` | `tlrm_availability_global`, `tlrm_open_booking_availability_wizard` |
| Sequence prefix | `TLRM/` | `TLRM/00001` |

## Security Groups

- **TL Rental User** (`tlrm_group_user`): Basic rental access (read, write, create)
- **TL Rental Manager** (`tlrm_group_manager`): Full access including delete

Stock users automatically inherit TL Rental User permissions.

## Models

### tl.rental.booking

Main booking header with:
- Project reference (required)
- Source/Rental warehouse
- Date range (start/end)
- State workflow: draft → reserved → ongoing → finished → returned

### tl.rental.booking.line

Booking lines with:
- Product and quantity
- Warehouse overrides per line
- Related fields from booking (dates, state, project)

## Availability Grid

The availability grid (`Inventory → Rental → Availability`) provides:

- Week-by-week view of product availability (12 weeks at a time)
- Gradient color-coded cells: green (0% booked) → yellow (75% booked) → red (100% booked)
- Click booked cells to drill-down to booking lines
- Search bar for filtering products by name/code
- Sortable product column (A-Z / Z-A)
- Week navigation (Previous / Today / Next)
- Hover effects on clickable cells

## Booking Availability Wizard

When creating a booking, use the **Check Availability** button to:

- View availability for all products in the booking lines
- Toggle between week and day views
- Click and drag to select a date range
- See per-product availability validation (green = fits, red = doesn't fit)
- Get a summary showing how many products fit the selected period
- Apply selected dates to the booking with one click

The wizard helps ensure all products are available before confirming a booking.

## Configuration

1. Install the module via Apps
2. Assign security groups to users:
   - **Rental User** for basic usage
   - **Rental Manager** for full CRUD access
3. (Optional) Adjust the scheduled action in *Settings → Technical → Scheduled Actions*

## Usage

1. Go to **Inventory → Rental → Bookings**
2. Create a new booking with project and warehouse
3. Add booking lines with products and quantities
4. Click **Check Availability** to find available dates for all products
5. Select a date range and click **Apply Dates**
6. Confirm to reserve stock
7. Use **Availability** view to check capacity across all products

## Technical Details

- **Availability computation**: `tl.rental.booking.line.get_availability_grid()`
- **Global availability grid**: `static/src/js/rental_availability_action.js`
- **Booking availability wizard**: `static/src/js/booking_availability_wizard.js`
- **Controller endpoints**:
  - `/tlrm/availability_grid/global`
  - `/tlrm/availability_grid/booking`

## Dependencies

- Odoo 19.0 Community
- Core modules: `base`, `product`, `stock`, `project`, `mail`

## License

LGPL-3
