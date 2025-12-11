# TL Rental Manager

Odoo 19 Community module for managing stockable product rentals with project-based bookings and availability planning.

## Features

- **Rental Bookings**: Create and manage rental bookings linked to projects
- **Availability Grid**: Visual week-by-week availability calendar for all products
- **Multi-warehouse Support**: Filter availability by warehouse or view aggregated totals
- **Dedicated Rental Location**: Each warehouse gets a "TL Rental Out" location for rented items
- **Stock Integration**: Automatic stock moves when confirming/returning rentals
- **Multi-company Support**: Full multi-company record rules
- **Calendar Integration**: Week numbers tuned for Swedish conventions
- **Top-level Menu**: Rental app appears in main sidebar (not under Inventory)

## Use Cases

- Rent out physical equipment (tools, machines, vehicles)
- Plan project-specific rentals and check stock availability
- Get a quick overview of booked vs available units per week
- Track which items are currently rented out vs available

## Module Structure

```
tl_rental_manager/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── controllers.py              # JSON-RPC endpoints
│       - /tlrm/availability_grid/global
│       - /tlrm/availability_grid/booking
│       - /tlrm/warehouses
├── data/
│   ├── rental_cron.xml             # Cron: _cron_notify_booking_status
│   ├── rental_sequence.xml         # Sequence: TLRM/xxxxx
│   └── stock_warehouse_data.xml    # Creates rental locations for existing warehouses
├── models/
│   ├── __init__.py
│   ├── product.py                  # product.template extensions (tlrm_* fields)
│   ├── rental_booking.py           # tl.rental.booking & tl.rental.booking.line
│   ├── stock_picking.py            # stock.picking extensions
│   └── stock_warehouse.py          # stock.warehouse extension (tlrm_rental_location_id)
├── security/
│   ├── ir.model.access.csv
│   └── rental_security.xml
├── static/
│   ├── description/
│   │   └── icon.svg                # App icon for main menu
│   └── src/
│       ├── css/
│       │   └── rental_availability.css
│       ├── js/
│       │   ├── booking_availability_action.js
│       │   ├── booking_availability_wizard.js
│       │   ├── rental_availability_action.js
│       │   └── rental_calendar.js
│       └── xml/
│           ├── booking_availability_wizard_templates.xml
│           └── rental_availability_templates.xml
└── views/
    ├── product_view.xml
    └── rental_booking_views.xml
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

### stock.warehouse (extension)

- `tlrm_rental_location_id`: Points to "TL Rental Out" location (auto-created)

### tl.rental.booking

Main booking header with:
- Project reference (required)
- Source warehouse (determines rental location)
- Date range (start/end)
- State workflow: draft → reserved → ongoing → finished → returned

### tl.rental.booking.line

Booking lines with:
- Product and quantity
- Related fields from booking (warehouse, dates, state)

## Availability Grid

The availability grid (`Rental → Availability`) provides:

- Week-by-week view of product availability (12 weeks at a time)
- **Warehouse filter dropdown**: View all warehouses aggregated or filter by specific warehouse
- Gradient color-coded cells: green (0% booked) → yellow (75% booked) → red (100% booked)
- Click booked cells to drill-down to booking lines
- Search bar for filtering products by name/code
- Sortable product column (A-Z / Z-A)
- Week navigation (Previous / Today / Next)
- Hover effects on clickable cells

## Booking Availability Wizard

When creating a booking, use the **Check Availability** button to:

- View availability for all products in the booking lines
- **Warehouse filter dropdown**: Check availability in specific warehouse or all
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
3. Each warehouse automatically gets a "TL Rental Out" location created
4. (Optional) Adjust the scheduled action in *Settings → Technical → Scheduled Actions*

## Usage

1. Go to **Rental → Bookings** (top-level menu)
2. Create a new booking with project and warehouse
3. Add booking lines with products and quantities
4. Click **Check Availability** to find available dates for all products
5. Select a date range and click **Apply Dates**
6. Confirm to reserve stock (creates outbound picking to "TL Rental Out")
7. Use **Availability** view to check capacity across all products
8. When rental ends, click **Return** to create return picking

## Technical Details

- **Availability computation**: `tl.rental.booking.line.get_availability_grid()`
- **Global availability grid**: `static/src/js/rental_availability_action.js`
- **Booking availability wizard**: `static/src/js/booking_availability_wizard.js`
- **Controller endpoints**:
  - `/tlrm/availability_grid/global` - Global availability data
  - `/tlrm/availability_grid/booking` - Booking-specific availability
  - `/tlrm/warehouses` - List of warehouses for filter dropdown

## Odoo 19 Specific Notes

This module uses Odoo 19 patterns. See `Odoo 19.md` for important technical notes:

- Uses `jsonrpc` import instead of `useService("rpc")` (removed in Odoo 19)
- Security groups defined without `category_id` (removed in Odoo 19)
- Uses `_read_group` instead of deprecated `read_group`

## Dependencies

- Odoo 19.0 Community
- Core modules: `base`, `product`, `stock`, `project`, `mail`

## License

LGPL-3
