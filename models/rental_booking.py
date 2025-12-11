from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class TlRentalBooking(models.Model):
    _name = 'tl.rental.booking'
    _description = 'TL Rental Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string="Booking Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))

    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    
    partner_id = fields.Many2one('res.partner', string="Customer", check_company=True)
    project_id = fields.Many2one('project.project', string="Project", check_company=True, required=True)

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Source Warehouse",
        required=True,
        check_company=True,
    )

    source_location_id = fields.Many2one(
        'stock.location',
        string="Source Location",
        related="source_warehouse_id.lot_stock_id",
        readonly=True,
    )
    rental_location_id = fields.Many2one(
        'stock.location',
        string="Rental Location",
        related="source_warehouse_id.tlrm_rental_location_id",
        readonly=True,
    )
    
    date_start = fields.Datetime(string="Start Date", default=fields.Datetime.now, tracking=True)
    date_end = fields.Datetime(string="End Date", tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('reserved', 'Reserved'),
        ('ongoing', 'Ongoing'),
        ('finished', 'Finished'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', tracking=True, group_expand='_expand_states')
    
    line_ids = fields.One2many('tl.rental.booking.line', 'booking_id', string="Lines")
    
    notes = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tl.rental.booking') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        for booking in self:
            # Validate header fields only when confirming
            if not booking.date_start:
                raise ValidationError(_("Start date is required."))
            if booking.date_start and not booking.date_end:
                raise ValidationError(_("End date is required."))
            if booking.date_start and booking.date_end and booking.date_start > booking.date_end:
                raise ValidationError(_("Start date cannot be after end date."))
            if not booking.project_id:
                raise ValidationError(_("Project is required for Rental bookings."))

            # Ensure all lines are complete and available when confirming
            for line in booking.line_ids:
                if not line.product_id:
                    raise ValidationError(_("Each line must have a product before confirming a booking."))
                if not line.source_warehouse_id:
                    raise ValidationError(_("Each line must have a Source Warehouse set."))
                line._check_line_availability()

            booking._create_start_picking()
            booking.state = 'reserved'

    def action_mark_ongoing(self):
        for booking in self:
            booking.state = 'ongoing'

    def action_finish(self):
        for booking in self:
            booking.state = 'finished'

    def action_return(self):
        for booking in self:
            booking._create_return_picking()
            booking.state = 'returned'

    def action_cancel(self):
        for booking in self:
            booking.state = 'cancelled'

    def action_check_availability(self):
        """Open the availability wizard for this booking's lines."""
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("Add booking lines first before checking availability."))
        
        # Return action that will be handled by JS to open the wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'tlrm_open_booking_availability_wizard',
            'params': {
                'booking_id': self.id,
                'booking_lines': [{
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'quantity': line.quantity,
                } for line in self.line_ids if line.product_id],
                'warehouse_id': self.source_warehouse_id.id if self.source_warehouse_id else None,
                'company_id': self.company_id.id,
            },
        }

    def write(self, vals):
        """Handle date updates from the availability wizard.
        
        When called with context key 'skip_date_tracking', we temporarily
        disable tracking on date fields to avoid chatter noise from the
        availability wizard (which is just a date picker).
        """
        if self.env.context.get('tlrm_skip_date_tracking'):
            # Temporarily disable tracking for date fields
            self = self.with_context(tracking_disable=True)
        return super().write(vals)
            
    def _expand_states(self, states, domain, order):
        return [key for key, val in type(self).state.selection]

    @api.model
    def get_dashboard_data(self):
        """Return KPI data for the rental dashboard."""
        company = self.env.company
        now = fields.Datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Count bookings by state
        state_counts = {}
        for state_key, state_label in self._fields['state'].selection:
            count = self.search_count([
                ('company_id', '=', company.id),
                ('state', '=', state_key),
            ])
            state_counts[state_key] = {'count': count, 'label': state_label}
        
        # Total bookings
        total_bookings = sum(s['count'] for s in state_counts.values())
        
        # Active rentals (reserved + ongoing)
        active_rentals = state_counts.get('reserved', {}).get('count', 0) + \
                        state_counts.get('ongoing', {}).get('count', 0)
        
        # Bookings starting today
        starting_today = self.search_count([
            ('company_id', '=', company.id),
            ('state', '=', 'reserved'),
            ('date_start', '>=', today_start),
            ('date_start', '<', today_start + timedelta(days=1)),
        ])
        
        # Bookings ending today (need return)
        ending_today = self.search_count([
            ('company_id', '=', company.id),
            ('state', 'in', ['reserved', 'ongoing']),
            ('date_end', '>=', today_start),
            ('date_end', '<', today_start + timedelta(days=1)),
        ])
        
        # Overdue bookings (past end date, not returned)
        overdue = self.search_count([
            ('company_id', '=', company.id),
            ('state', 'in', ['reserved', 'ongoing', 'finished']),
            ('date_end', '<', now),
        ])
        
        # Recent bookings (last 10)
        recent_bookings = self.search_read(
            [('company_id', '=', company.id)],
            ['name', 'project_id', 'date_start', 'date_end', 'state'],
            limit=10,
            order='create_date desc',
        )
        
        # Products currently rented out (in TL Rental Out locations)
        rental_locations = self.env['stock.warehouse'].search([
            ('company_id', '=', company.id),
            ('tlrm_rental_location_id', '!=', False),
        ]).mapped('tlrm_rental_location_id')
        
        products_out = 0
        if rental_locations:
            quants = self.env['stock.quant'].search([
                ('location_id', 'in', rental_locations.ids),
                ('quantity', '>', 0),
            ])
            products_out = len(quants.mapped('product_id'))
        
        return {
            'total_bookings': total_bookings,
            'active_rentals': active_rentals,
            'starting_today': starting_today,
            'ending_today': ending_today,
            'overdue': overdue,
            'products_out': products_out,
            'state_counts': state_counts,
            'recent_bookings': recent_bookings,
        }

    @api.model
    def _cron_notify_booking_status(self):
        now = fields.Datetime.now()
        
        # Reserved -> should start
        bookings_to_start = self.search([
            ('state', '=', 'reserved'),
            ('date_start', '<=', now),
            ('date_end', '>', now)
        ])
        for booking in bookings_to_start:
            booking.message_post(body=_("Rental booking %s should start based on its planned dates.") % booking.name)
        
        # Reserved/Ongoing -> should be finished
        bookings_to_finish = self.search([
            ('state', 'in', ['reserved', 'ongoing']),
            ('date_end', '<=', now)
        ])
        for booking in bookings_to_finish:
            booking.message_post(body=_("Rental booking %s has passed its end date and should be finished/returned.") % booking.name)

    def _group_lines_by_warehouse(self):
        """Group booking lines by source_warehouse_id.
        
        :return: dict mapping source_wh_id to list of lines
        """
        self.ensure_one()
        lines_by_wh = {}
        for line in self.line_ids:
            if not line.product_id or line.quantity <= 0:
                continue
            if not line.source_warehouse_id:
                continue
            key = line.source_warehouse_id.id
            lines_by_wh.setdefault(key, []).append(line)
        return lines_by_wh

    def _prepare_picking_vals(self, picking_type, location_id, location_dest_id, direction):
        """Prepare values for stock.picking creation.
        
        :param picking_type: stock.picking.type record
        :param location_id: source stock.location id
        :param location_dest_id: destination stock.location id
        :param direction: 'out' for rental start, 'in' for rental return
        :return: dict of values for stock.picking.create()
        """
        self.ensure_one()
        return {
            'picking_type_id': picking_type.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'tlrm_booking_id': self.id,
            'tlrm_direction': direction,
        }

    def _prepare_move_vals(self, line, picking, location_id, location_dest_id):
        """Prepare values for stock.move creation.
        
        :param line: tl.rental.booking.line record
        :param picking: stock.picking record
        :param location_id: source stock.location id
        :param location_dest_id: destination stock.location id
        :return: dict of values for stock.move.create()
        """
        return {
            'product_id': line.product_id.id,
            'product_uom': line.product_id.uom_id.id,
            'product_uom_qty': line.quantity,
            'picking_id': picking.id,
            'company_id': self.company_id.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
        }

    def _create_picking_for_direction(self, direction):
        """Create stock picking(s) for the given direction.
        
        :param direction: 'out' for rental start (source -> TL Rental Out location),
                          'in' for rental return (TL Rental Out -> source location)
        """
        Picking = self.env['stock.picking']
        Move = self.env['stock.move']

        for booking in self:
            lines_by_wh = booking._group_lines_by_warehouse()

            for source_wh_id, lines in lines_by_wh.items():
                source_wh = self.env['stock.warehouse'].browse(source_wh_id)
                source_location = source_wh.lot_stock_id
                rental_location = source_wh.tlrm_rental_location_id

                if not source_location or not rental_location:
                    continue

                if direction == 'out':
                    picking_type = source_wh.int_type_id
                    location_id = source_location.id
                    location_dest_id = rental_location.id
                else:  # 'in'
                    picking_type = source_wh.int_type_id
                    location_id = rental_location.id
                    location_dest_id = source_location.id

                if not picking_type:
                    continue

                picking_vals = booking._prepare_picking_vals(
                    picking_type, location_id, location_dest_id, direction
                )
                picking = Picking.create(picking_vals)

                for line in lines:
                    move_vals = booking._prepare_move_vals(
                        line, picking, location_id, location_dest_id
                    )
                    Move.create(move_vals)

                picking.action_confirm()
                picking.action_assign()

    def _create_start_picking(self):
        """Create picking(s) to move products from source to rental location."""
        self._create_picking_for_direction('out')

    def _create_return_picking(self):
        """Create picking(s) to move products from rental back to source location."""
        self._create_picking_for_direction('in')


class TlRentalBookingLine(models.Model):
    _name = 'tl.rental.booking.line'
    _description = 'TL Rental Booking Line'

    booking_id = fields.Many2one('tl.rental.booking', string="Booking", required=True, ondelete="cascade")
    company_id = fields.Many2one(related='booking_id.company_id', store=True)
    project_id = fields.Many2one(related='booking_id.project_id', store=True, string="Project")
    source_warehouse_id = fields.Many2one('stock.warehouse', string="Source Warehouse", check_company=True)
    source_location_id = fields.Many2one(
        'stock.location',
        string="Source Location",
        related="source_warehouse_id.lot_stock_id",
        readonly=True,
    )
    rental_location_id = fields.Many2one(
        'stock.location',
        string="Rental Location",
        related="source_warehouse_id.tlrm_rental_location_id",
        readonly=True,
    )
    
    product_id = fields.Many2one('product.product', string="Product")
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit of Measure')
    
    date_start = fields.Datetime(related='booking_id.date_start', store=True)
    date_end = fields.Datetime(related='booking_id.date_end', store=True)
    state = fields.Selection(related='booking_id.state', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure warehouse field is populated from booking header if not set."""
        for vals in vals_list:
            if vals.get('booking_id') and not vals.get('source_warehouse_id'):
                booking = self.env['tl.rental.booking'].browse(vals['booking_id'])
                if booking.source_warehouse_id:
                    vals['source_warehouse_id'] = booking.source_warehouse_id.id
        return super().create(vals_list)

    @api.onchange('booking_id')
    def _onchange_booking_id(self):
        for line in self:
            if line.booking_id and not line.source_warehouse_id:
                line.source_warehouse_id = line.booking_id.source_warehouse_id

    def _check_line_availability(self):
        """Check if the requested quantity exceeds available stock.
        
        Uses physical stock (stock.quant.quantity) minus overlapping 'reserved'
        booking lines. Ongoing bookings are not counted since they already
        reduced the physical stock.
        """
        for line in self:
            if not line.product_id or not line.date_start or not line.date_end:
                continue

            if line.quantity <= 0:
                continue

            product = line.product_id
            company = line.company_id or self.env.company

            # Filter by source warehouse - use line's warehouse or fall back to booking header
            source_wh = line.source_warehouse_id or line.booking_id.source_warehouse_id
            source_location = source_wh.lot_stock_id if source_wh else None
            
            # Get physical stock from quants (ignoring Odoo's reserved_quantity)
            if source_location:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', source_location.id),
                ])
                base_capacity = sum(quants.mapped('quantity'))
            else:
                base_capacity = 0.0
            
            logger.info(
                "Availability check for %s in warehouse %s (location %s): qty_available=%s",
                product.display_name,
                source_wh.name if source_wh else 'N/A',
                source_location.complete_name if source_location else 'N/A',
                base_capacity,
            )

            if base_capacity <= 0:
                raise ValidationError(_(
                    "No available stock for product '%s' in the selected warehouse '%s'."
                ) % (product.display_name, source_wh.name if source_wh else 'N/A'))

            domain = [
                ('id', '!=', line.id),
                ('product_id', '=', product.id),
                ('company_id', '=', company.id if company else False),
                ('state', '=', 'reserved'),  # Only reserved - ongoing already reduced qty_on_hand
                ('date_start', '<', line.date_end),
                ('date_end', '>', line.date_start),
            ]
            # Also filter overlapping bookings by the same source warehouse
            if source_wh:
                domain.append(('source_warehouse_id', '=', source_wh.id))
            overlapping_lines = self.search(domain)
            current_booked_qty = sum(overlapping_lines.mapped('quantity'))

            if current_booked_qty + line.quantity > base_capacity:
                raise ValidationError(_(
                    "Not enough availability for product '%s' during this period.\n"
                    "Available capacity: %s\n"
                    "Already booked: %s\n"
                    "Requested: %s"
                ) % (product.display_name, base_capacity, current_booked_qty, line.quantity))

    @api.constrains('product_id', 'date_start', 'date_end', 'state', 'company_id', 'quantity')
    def _constrains_check_availability(self):
        for line in self:
            if line.state in ['reserved', 'ongoing', 'finished']:
                line._check_line_availability()

    @api.model
    def _normalize_grid_params(self, product_ids, week_count, company_id, needed_by_product):
        """Normalize and validate input parameters for availability grid.
        
        :return: tuple (product_ids, week_count, company, needed_by_product)
        """
        if not product_ids:
            product_ids = []
        elif isinstance(product_ids, int):
            product_ids = [product_ids]

        week_count = int(week_count or 0)
        if week_count <= 0:
            week_count = 12
        max_week_count = 20
        if week_count > max_week_count:
            week_count = max_week_count

        company = self.env['res.company'].browse(company_id) if company_id else self.env.company
        needed_by_product = needed_by_product or {}

        return product_ids, week_count, company, needed_by_product

    @api.model
    def _compute_weeks(self, date_start, week_count):
        """Compute week periods aligned to Monday (ISO week).
        
        :param date_start: reference date (datetime or string)
        :param week_count: number of weeks to generate
        :return: list of week dicts with key, label, start_dt, end_dt
        """
        if date_start:
            base_dt = fields.Datetime.to_datetime(date_start)
        else:
            base_dt = fields.Datetime.now()

        base_date = base_dt.date()
        weekday = base_date.weekday()  # Monday = 0
        monday_date = base_date - timedelta(days=weekday)
        monday_dt = datetime.combine(monday_date, datetime.min.time())

        weeks = []
        for index in range(week_count):
            week_start_dt = monday_dt + timedelta(weeks=index)
            week_end_dt = week_start_dt + timedelta(days=7)
            iso_year, iso_week, _ = week_start_dt.isocalendar()
            column_key = f"{iso_year}-W{iso_week:02d}"
            weeks.append({
                'key': column_key,
                'label': f"V.{iso_week}",
                'start_dt': week_start_dt,
                'end_dt': week_end_dt,
            })
        return weeks

    @api.model
    def _get_base_capacity(self, product_ids, warehouse_id, company):
        """Get physical stock capacity per product from stock.quant.
        
        Uses stock.quant.quantity (physical stock) to avoid double-counting
        with our booking reservation layer.
        
        :param product_ids: list of product.product ids
        :param warehouse_id: optional stock.warehouse id for location filtering
        :param company: res.company record for filtering warehouses
        :return: dict mapping product_id to physical quantity
        """
        base_capacity = defaultdict(float)
        if not product_ids:
            return base_capacity

        Quant = self.env['stock.quant']

        if warehouse_id:
            warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            if warehouse.exists() and warehouse.lot_stock_id:
                quants = Quant.search([
                    ('product_id', 'in', product_ids),
                    ('location_id', 'child_of', warehouse.lot_stock_id.id),
                ])
                for quant in quants:
                    base_capacity[quant.product_id.id] += quant.quantity
        else:
            warehouses = self.env['stock.warehouse'].search([
                ('company_id', '=', company.id)
            ])
            location_ids = warehouses.mapped('lot_stock_id').ids
            if location_ids:
                quants = Quant.search([
                    ('product_id', 'in', product_ids),
                    ('location_id', 'child_of', location_ids),
                ])
                for quant in quants:
                    base_capacity[quant.product_id.id] += quant.quantity

        # Ensure non-negative values
        for pid in product_ids:
            base_capacity[pid] = max(base_capacity[pid], 0.0)

        return base_capacity

    @api.model
    def _get_booked_by_product_week(self, product_ids, weeks, warehouse_id, company):
        """Compute booked quantities per product and week from existing booking lines.
        
        :param product_ids: list of product.product ids
        :param weeks: list of week dicts from _compute_weeks
        :param warehouse_id: optional stock.warehouse id for filtering
        :param company: res.company record
        :return: nested defaultdict mapping product_id -> week_key -> booked_qty
        """
        booked = defaultdict(lambda: defaultdict(float))
        if not product_ids or not weeks:
            return booked

        overall_start_dt = weeks[0]['start_dt']
        overall_end_dt = weeks[-1]['end_dt']

        domain = [
            ('product_id', 'in', product_ids),
            ('company_id', '=', company.id),
            ('state', '=', 'reserved'),  # Only reserved - ongoing already reduced qty_on_hand
            ('date_start', '<', fields.Datetime.to_string(overall_end_dt)),
            ('date_end', '>', fields.Datetime.to_string(overall_start_dt)),
        ]
        if warehouse_id:
            domain.append(('source_warehouse_id', '=', warehouse_id))

        lines = self.search(domain)
        for line in lines:
            if not line.product_id:
                continue
            pid = line.product_id.id
            line_start = fields.Datetime.to_datetime(line.date_start) if line.date_start else None
            line_end = fields.Datetime.to_datetime(line.date_end) if line.date_end else None
            if not line_start or not line_end:
                continue
            for week in weeks:
                # Overlap check: [line_start, line_end) vs [week_start, week_end)
                if line_start < week['end_dt'] and line_end > week['start_dt']:
                    booked[pid][week['key']] += line.quantity

        return booked

    @api.model
    def _build_grid_columns(self, weeks):
        """Build column descriptors for the frontend grid.
        
        :param weeks: list of week dicts from _compute_weeks
        :return: list of column dicts with key, label, start, end
        """
        return [
            {
                'key': week['key'],
                'label': week['label'],
                'start': fields.Datetime.to_string(week['start_dt']),
                'end': fields.Datetime.to_string(week['end_dt']),
            }
            for week in weeks
        ]

    @api.model
    def _compute_cell_status(self, available, needed):
        """Determine cell status and booking_ok flag.
        
        :param available: available quantity
        :param needed: needed quantity (or None)
        :return: tuple (status, booking_ok)
        """
        if needed is not None and needed > 0:
            if available >= needed:
                return 'free', True
            elif available > 0:
                return 'partial', False
            else:
                return 'full', False
        else:
            if available <= 0:
                return 'full', None
            else:
                return 'free', None

    @api.model
    def _build_grid_rows(self, product_ids, weeks, base_capacity_by_product,
                         booked_by_product_week, needed_by_product):
        """Build row data for each product in the grid.
        
        :param product_ids: list of product.product ids
        :param weeks: list of week dicts
        :param base_capacity_by_product: dict from _get_base_capacity
        :param booked_by_product_week: nested dict from _get_booked_by_product_week
        :param needed_by_product: dict mapping product_id to needed quantity
        :return: list of row dicts for the grid
        """
        products = self.env['product.product'].browse(product_ids)
        rows = []

        for product in products:
            base_capacity = float(base_capacity_by_product.get(product.id, 0.0) or 0.0)
            needed = float(needed_by_product.get(product.id, 0.0) or 0.0)
            cell_needed = needed if needed > 0.0 else None
            cells = []

            for week in weeks:
                week_key = week['key']
                booked = float(booked_by_product_week[product.id].get(week_key, 0.0) or 0.0)
                available = max(base_capacity - booked, 0.0)
                status, booking_ok = self._compute_cell_status(available, cell_needed)

                try:
                    tooltip = _(
                        "Booked: %(booked)s, Available: %(available)s",
                        booked=booked,
                        available=available,
                    )
                except Exception:
                    tooltip = None

                cells.append({
                    'column_key': week_key,
                    'booked': booked,
                    'available': available,
                    'needed': cell_needed,
                    'status': status,
                    'booking_ok': booking_ok,
                    'tooltip': tooltip,
                })

            rows.append({
                'product_id': product.id,
                'display_name': product.display_name,
                'default_code': product.default_code,
                'uom_name': product.uom_id.name,
                'base_capacity': base_capacity,
                'needed': cell_needed,
                'cells': cells,
            })

        return rows

    @api.model
    def get_availability_grid(
        self,
        product_ids,
        date_start,
        week_count=12,
        warehouse_id=None,
        company_id=None,
        needed_by_product=None,
    ):
        """Return a per-product, per-week availability grid for rentals.

        :param product_ids: list of product.product ids to include as rows.
        :param date_start: reference date (datetime or string); grid is aligned to the
            Monday of the week containing this date.
        :param week_count: number of weeks to include (capped at 20).
        :param warehouse_id: optional stock.warehouse id used as source warehouse
            for capacity and booking-lines filtering.
        :param company_id: optional res.company id; defaults to current company.
        :param needed_by_product: optional dict {product_id: qty} used mainly for
            booking-specific views to highlight if capacity is sufficient.
        :return: dict with ``meta``, ``columns`` and ``rows`` suitable for OWL grids.
        """
        # Normalize inputs
        product_ids, week_count, company, needed_by_product = self._normalize_grid_params(
            product_ids, week_count, company_id, needed_by_product
        )
        self = self.with_context(allowed_company_ids=[company.id])

        # Compute week periods
        weeks = self._compute_weeks(date_start, week_count)

        # Get overall date range
        if weeks:
            overall_start_dt = weeks[0]['start_dt']
            overall_end_dt = weeks[-1]['end_dt']
        else:
            overall_start_dt = fields.Datetime.now()
            overall_end_dt = overall_start_dt

        # Get base capacity and booked quantities
        base_capacity_by_product = self._get_base_capacity(product_ids, warehouse_id, company)
        booked_by_product_week = self._get_booked_by_product_week(
            product_ids, weeks, warehouse_id, company
        )

        # Build grid structure
        columns = self._build_grid_columns(weeks)
        rows = self._build_grid_rows(
            product_ids, weeks, base_capacity_by_product,
            booked_by_product_week, needed_by_product
        )

        return {
            'meta': {
                'company_id': company.id,
                'warehouse_id': warehouse_id,
                'date_start': fields.Datetime.to_string(overall_start_dt),
                'date_end': fields.Datetime.to_string(overall_end_dt),
                'week_count': week_count,
            },
            'columns': columns,
            'rows': rows,
        }
