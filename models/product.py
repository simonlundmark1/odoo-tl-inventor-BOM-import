from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    tlrm_price_hour = fields.Monetary(string="Rental Price per Hour")
    tlrm_price_day = fields.Monetary(string="Rental Price per Day")
    tlrm_price_week = fields.Monetary(string="Rental Price per Week")
    
    tlrm_min_hours = fields.Float(string="Min. Rental Hours", default=1.0)
    tlrm_min_days = fields.Float(string="Min. Rental Days", default=0.0)
    tlrm_min_weeks = fields.Float(string="Min. Rental Weeks", default=0.0)
    
    tlrm_fleet_capacity = fields.Float(
        string="Fleet Capacity",
        compute="_compute_tlrm_fleet_capacity",
        store=False,
        help="Total units owned for rental, computed from stock.quant across "
             "all internal locations. This is the theoretical maximum available "
             "for booking, regardless of current physical location."
    )
    
    tlrm_planned_units = fields.Integer(
        string="Planned Units", 
        compute="_compute_tlrm_counts", 
        store=False,
        help="Units in planned bookings (blocks availability for planning)."
    )
    tlrm_reserved_units = fields.Integer(
        string="Reserved Units",
        compute="_compute_tlrm_counts",
        store=False,
        help="Units reserved with pickings created (hard commitment)."
    )
    tlrm_rented_units = fields.Integer(
        string="Rented Units", 
        compute="_compute_tlrm_counts", 
        store=False,
        help="Units currently in ongoing bookings."
    )
    tlrm_available_units = fields.Integer(
        string="Available Units", 
        compute="_compute_tlrm_counts", 
        store=False
    )
    
    tlrm_status = fields.Selection([
        ('available', 'Available'),
        ('planned', 'Planned'),
        ('rented', 'Rented'),
        ('unavailable', 'Unavailable'),
    ], string="Rental Status", compute="_compute_tlrm_status", store=False)

    def _compute_tlrm_fleet_capacity(self):
        """Compute fleet capacity from stock.quant across all internal locations.
        
        This sums the 'quantity' field from stock.quant for all product variants
        in internal locations within the current company.
        """
        for product in self:
            product.tlrm_fleet_capacity = 0.0
        
        if not self:
            return
        
        # Collect all variant IDs
        all_variant_ids = self.mapped('product_variant_ids').ids
        if not all_variant_ids:
            return
        
        Quant = self.env['stock.quant']
        company_id = self.env.company.id
        
        # Sum quantities across all internal locations
        domain = [
            ('product_id', 'in', all_variant_ids),
            ('company_id', '=', company_id),
            ('location_id.usage', '=', 'internal'),
        ]
        groups = Quant._read_group(
            domain,
            groupby=['product_id'],
            aggregates=['quantity:sum'],
        )
        
        # Build lookup: product_id -> total quantity
        qty_by_product = {}
        for product_id, qty_sum in groups:
            pid = product_id.id if product_id else False
            qty_by_product[pid] = qty_sum or 0.0
        
        # Assign fleet capacity to each template
        for product in self:
            total = 0.0
            for variant in product.product_variant_ids:
                total += qty_by_product.get(variant.id, 0.0)
            product.tlrm_fleet_capacity = total

    @api.depends('tlrm_available_units', 'tlrm_planned_units', 'tlrm_rented_units')
    def _compute_tlrm_status(self):
        for product in self:
            if product.tlrm_rented_units > 0:
                product.tlrm_status = 'rented'
            elif product.tlrm_planned_units > 0:
                product.tlrm_status = 'planned'
            elif product.tlrm_available_units <= 0:
                product.tlrm_status = 'unavailable'
            else:
                product.tlrm_status = 'available'

    def _compute_tlrm_counts(self):
        """Compute rental availability counts using fleet capacity.
        
        Uses read_group for efficient batch querying instead of multiple searches.
        
        - Planned: Units in 'planned' state (blocks availability for planning)
        - Reserved: Units in 'reserved' state (hard lock, stock movements created)
        - Rented: Units in 'ongoing' or 'finished' state (physically out)
        - Available: Fleet capacity minus planned, reserved and rented units
        """
        # Initialize all products with zero values
        for product in self:
            product.tlrm_planned_units = 0
            product.tlrm_reserved_units = 0
            product.tlrm_rented_units = 0
            product.tlrm_available_units = 0
        
        if not self:
            return
        
        # Collect all variant IDs for batch query
        all_variant_ids = self.mapped('product_variant_ids').ids
        if not all_variant_ids:
            return
        
        BookingLine = self.env['tl.rental.booking.line']
        company_id = self.env.company.id
        
        # Single read_group query for all states
        domain = [
            ('product_id', 'in', all_variant_ids),
            ('state', 'in', ['planned', 'reserved', 'ongoing', 'finished']),
            ('company_id', '=', company_id),
        ]
        groups = BookingLine._read_group(
            domain,
            groupby=['product_id', 'state'],
            aggregates=['quantity:sum'],
        )
        
        # Build lookup: product_id -> state -> quantity
        qty_by_product_state = {}
        for product_id, state, qty_sum in groups:
            pid = product_id.id if product_id else False
            if pid not in qty_by_product_state:
                qty_by_product_state[pid] = {}
            qty_by_product_state[pid][state] = qty_sum or 0.0
        
        # Assign values to each product template
        for product in self:
            planned = 0.0
            reserved = 0.0
            rented = 0.0
            
            for variant in product.product_variant_ids:
                state_qtys = qty_by_product_state.get(variant.id, {})
                planned += state_qtys.get('planned', 0.0)
                reserved += state_qtys.get('reserved', 0.0)
                rented += state_qtys.get('ongoing', 0.0) + state_qtys.get('finished', 0.0)
            
            fleet_capacity = product.tlrm_fleet_capacity or 0.0
            # Planned, reserved, and rented all reduce availability
            available = fleet_capacity - planned - reserved - rented
            
            product.tlrm_planned_units = int(planned)
            product.tlrm_reserved_units = int(reserved)
            product.tlrm_rented_units = int(rented)
            product.tlrm_available_units = int(max(available, 0.0))

