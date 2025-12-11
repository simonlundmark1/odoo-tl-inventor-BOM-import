from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    tlrm_booking_id = fields.Many2one('tl.rental.booking', string="Rental Booking")
    tlrm_direction = fields.Selection([
        ('out', 'Rental Out'),
        ('in', 'Rental In'),
    ], string="Rental Direction")

    def button_validate(self):
        """Auto-fill done quantities for rental pickings before validation."""
        for picking in self:
            if picking.tlrm_booking_id and picking.tlrm_direction:
                for move in picking.move_ids:
                    if move.quantity == 0 and move.product_uom_qty > 0:
                        move.quantity = move.product_uom_qty
        return super().button_validate()

    def _action_done(self):
        """Update booking state when picking is completed."""
        res = super()._action_done()
        for picking in self:
            booking = picking.tlrm_booking_id
            if not booking:
                continue
            if picking.tlrm_direction == 'out' and booking.state == 'reserved':
                booking.state = 'ongoing'
            elif picking.tlrm_direction == 'in':
                if booking.state in ['ongoing', 'finished']:
                    booking.state = 'returned'
        return res
