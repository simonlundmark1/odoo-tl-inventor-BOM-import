from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class StockRentalBooking(models.Model):
    _name = 'stock.rental.booking'
    _description = 'Stock Rental Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string="Booking Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    booking_type = fields.Selection([
        ('rental', 'Rental'),
        ('project', 'Project Booking')
    ], string="Booking Type", default='rental', required=True)
    
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    
    partner_id = fields.Many2one('res.partner', string="Customer", check_company=True)
    project_id = fields.Many2one('project.project', string="Project", check_company=True)
    
    date_start = fields.Datetime(string="Start Date", required=True, default=fields.Datetime.now, tracking=True)
    date_end = fields.Datetime(string="End Date", required=True, tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('reserved', 'Reserved'),
        ('ongoing', 'Ongoing'),
        ('finished', 'Finished'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', tracking=True, group_expand='_expand_states')
    
    line_ids = fields.One2many('stock.rental.booking.line', 'booking_id', string="Lines")
    
    notes = fields.Text(string="Notes")

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.rental.booking') or _('New')
        return super().create(vals)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for booking in self:
            if booking.date_start and booking.date_end and booking.date_start > booking.date_end:
                raise ValidationError(_("Start date cannot be after end date."))

    @api.constrains('booking_type', 'partner_id', 'project_id')
    def _check_booking_type_requirements(self):
        for booking in self:
            if booking.booking_type == 'rental' and not booking.partner_id:
                raise ValidationError(_("Customer is required for Rental bookings."))
            if booking.booking_type == 'project' and not booking.project_id:
                raise ValidationError(_("Project is required for Project bookings."))

    def action_confirm(self):
        for booking in self:
            # Check availability for all lines
            for line in booking.line_ids:
                line._check_line_availability()
            booking.state = 'reserved'

    def action_mark_ongoing(self):
        for booking in self:
            booking.state = 'ongoing'

    def action_finish(self):
        for booking in self:
            booking.state = 'finished'

    def action_return(self):
        for booking in self:
            booking.state = 'returned'
            # Trigger availability recomputation? 
            # The compute method on product depends on state, so it should update.

    def action_cancel(self):
        for booking in self:
            booking.state = 'cancelled'
            
    def _expand_states(self, states, domain, order):
        return [key for key, val in type(self).state.selection]

    @api.model
    def _cron_update_booking_states(self):
        now = fields.Datetime.now()
        
        # Reserved -> Ongoing
        bookings_to_start = self.search([
            ('state', '=', 'reserved'),
            ('date_start', '<=', now),
            ('date_end', '>', now)
        ])
        bookings_to_start.action_mark_ongoing()
        
        # Reserved/Ongoing -> Finished
        # Note: If it was reserved and expired without being ongoing, it finishes too.
        bookings_to_finish = self.search([
            ('state', 'in', ['reserved', 'ongoing']),
            ('date_end', '<=', now)
        ])
        bookings_to_finish.action_finish()


class StockRentalBookingLine(models.Model):
    _name = 'stock.rental.booking.line'
    _description = 'Stock Rental Booking Line'

    booking_id = fields.Many2one('stock.rental.booking', string="Booking", required=True, ondelete="cascade")
    company_id = fields.Many2one(related='booking_id.company_id', store=True)
    
    product_id = fields.Many2one('product.product', string="Product", required=True, check_company=True)
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit of Measure')
    
    date_start = fields.Datetime(related='booking_id.date_start', store=True)
    date_end = fields.Datetime(related='booking_id.date_end', store=True)
    state = fields.Selection(related='booking_id.state', store=True)

    @api.onchange('booking_id')
    def _onchange_booking_type_domain(self):
        pass

    def _check_line_availability(self):
        """
        Check if adding this line would exceed the product's rental_total_units
        during the booking period.
        """
        for line in self:
            if not line.product_id or not line.date_start or not line.date_end:
                continue
            
            if line.quantity <= 0:
                continue

            total_units = line.product_id.product_tmpl_id.rental_total_units
            
            # Find overlapping bookings for the same product and company
            # Overlap logic: StartA <= EndB AND EndA >= StartB
            domain = [
                ('id', '!=', line.id),
                ('product_id', '=', line.product_id.id),
                ('company_id', '=', line.company_id.id),
                ('state', 'in', ['reserved', 'ongoing', 'finished']), # Finished items not returned count as occupied
                ('date_start', '<', line.date_end),
                ('date_end', '>', line.date_start),
            ]
            
            overlapping_lines = self.search(domain)
            current_booked_qty = sum(overlapping_lines.mapped('quantity'))
            
            if current_booked_qty + line.quantity > total_units:
                raise ValidationError(_(
                    "Not enough availability for product '%s' during this period.\n"
                    "Total units: %s\n"
                    "Already booked: %s\n"
                    "Requested: %s"
                ) % (line.product_id.display_name, total_units, current_booked_qty, line.quantity))

    @api.constrains('product_id', 'date_start', 'date_end', 'state', 'company_id', 'quantity')
    def _constrains_check_availability(self):
        for line in self:
            if line.state in ['reserved', 'ongoing', 'finished']:
                line._check_line_availability()
