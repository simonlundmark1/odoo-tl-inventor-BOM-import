from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_booking_id = fields.Many2one('stock.rental.booking', string="Rental Booking")
    rental_direction = fields.Selection([
        ('out', 'Rental Out'),
        ('in', 'Rental In'),
    ], string="Rental Direction")

    def action_done(self):
        res = super().action_done()
        for picking in self:
            booking = picking.rental_booking_id
            if not booking:
                continue
            if picking.rental_direction == 'out' and booking.state == 'reserved':
                booking.state = 'ongoing'
            elif picking.rental_direction == 'in':
                if booking.state in ['ongoing', 'finished']:
                    booking.state = 'returned'
        return res
