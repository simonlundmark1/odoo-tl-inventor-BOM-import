TL Rental Manager
=================

Overview
--------

TL Rental Manager adds rental management on top of stockable products and
projects. It lets you:

- Plan and track product rentals by period.
- Link rentals to projects or tasks.
- Check availability with a week‑based capacity grid.
- Keep stock and reservations consistent during the rental lifecycle.

Use Cases
---------

- Rent out physical equipment (tools, machines, vehicles).
- Plan project‑specific rentals and see if stock is sufficient.
- Get a quick overview of booked vs available units per week.

Main Features
-------------

- Rental bookings with lines, periods and states (draft, reserved, ongoing, finished).
- Automatic booking sequence and scheduled job to update states.
- Availability grid per product and week, based on `stock.quant` and existing bookings.
- Calendar integration with week numbers tuned for Swedish conventions.
- Multi‑company aware domains and record rules.
- Dedicated security groups for rental users and managers.

Configuration
-------------

1. Install the module *TL Rental Manager*.
2. Assign security groups:

   - **Rental User** (basic usage).
   - **Rental Manager** (full CRUD, configuration).

3. (Optional) Adjust the scheduled action:

   - *Settings → Technical → Automation → Scheduled Actions*
   - **Stock Rental Booking: Update States**

Usage
-----

- Go to **Inventory / Rentals** (or your configured menu entry).
- Create a **Rental Booking**:
  
  - Select customer, company and rental period.
  - Add **Rental Booking Lines** with products and quantities.
  - Confirm to reserve stock.

- Open the **Rental Availability** action to:

  - See weekly capacity per product.
  - Check booked vs available units.
  - Drill down to the product form from the grid.

Security
--------

- Access rights are defined per model and group in
  `[security/ir.model.access.csv](cci:7://file:///c:/odoo_custom_addons/tl-rental-manager/security/ir.model.access.csv:0:0-0:0)`.
- Multi‑company access is enforced via record rules in
  `[security/rental_security.xml](cci:7://file:///c:/odoo_custom_addons/tl-rental-manager/security/rental_security.xml:0:0-0:0)`.
- Sequences are protected with ``noupdate="1"`` to avoid changes on upgrade.

Technical Details
-----------------

- Models:

  - ``stock.rental.booking``
  - ``stock.rental.booking.line``

- Key technical components:

  - Availability computation in
    `[stock.rental.booking.line.get_availability_grid](cci:1://file:///c:/odoo_custom_addons/stock_rental_manager/models/rental_booking.py:337:4-556:21)`.
  - OWL front‑end action and template for the availability grid:

    - JS: `[static/src/js/rental_availability_action.js](cci:7://file:///c:/odoo_custom_addons/tl-rental-manager/static/src/js/rental_availability_action.js:0:0-0:0)`
    - XML: `[static/src/xml/rental_availability_templates.xml](cci:7://file:///c:/odoo_custom_addons/tl-rental-manager/static/src/xml/rental_availability_templates.xml:0:0-0:0)`

  - Controller endpoints for JSON availability:

    - ``/stock_rental/availability_grid/global``
    - ``/stock_rental/availability_grid/booking``

Dependencies
------------

- Odoo 19.0 Community
- Core modules: ``base``, ``product``, ``stock``, ``project``, ``mail``

License
-------

This module is licensed under the LGPL‑3 license.
